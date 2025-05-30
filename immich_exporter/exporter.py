import faulthandler
import logging
import os
import signal
import sys
import time

import psutil
import requests
from prometheus_client import start_http_server
from prometheus_client.core import REGISTRY, CounterMetricFamily, GaugeMetricFamily
from pythonjsonlogger import jsonlogger

# Enable dumps on stderr in case of segfault
faulthandler.enable()
logger = logging.getLogger()


class ImmichMetricsCollector:
    def __init__(self, config):
        self.config = config

    def request(self, endpoint):
        response = requests.request(
            "GET",
            self.combine_url(endpoint),
            headers={"Accept": "application/json", "x-api-key": self.config["token"]},
        )
        return response

    def collect(self):
        logger.info("Requested the metrics")
        metrics = self.get_immich_metrics()

        for metric in metrics:
            name = metric["name"]
            value = metric["value"]
            help_text = metric.get("help", "")
            labels = metric.get("labels", {})
            metric_type = metric.get("type", "gauge")

            if metric_type == "counter":
                prom_metric = CounterMetricFamily(name, help_text, labels=labels.keys())
            else:
                prom_metric = GaugeMetricFamily(name, help_text, labels=labels.keys())
            prom_metric.add_metric(value=value, labels=labels.values())
            yield prom_metric
            logger.debug(prom_metric)

    def get_immich_metrics(self):
        metrics = []
        metrics.extend(self.get_immich_server_version_number())
        metrics.extend(self.get_immich_storage())
        metrics.extend(self.get_immich_users_stat())
        metrics.extend(self.get_system_stats())

        return metrics

    def get_immich_users_stat(self):
        try:
            endpoint_user_stats = "/statistics"

            response_user_stats = self.request(endpoint_user_stats).json()
        except requests.exceptions.RequestException as e:
            logger.error("API ERROR: can't get server statistic: %s", e)

        user_data = response_user_stats["usageByUser"]
        user_count = len(response_user_stats["usageByUser"])
        photos_growth_total = 0
        videos_growth_total = 0
        usage_growth_total = 0

        metrics = []

        for x in range(0, user_count):
            photos_growth_total += user_data[x]["photos"]
            videos_growth_total += user_data[x]["videos"]
            usage_growth_total += user_data[x]["usage"]
            metrics.append(
                {
                    "name": f"{self.config['metrics_prefix']}_server_stats_photos_by_users",
                    "value": user_data[x]["photos"],
                    "labels": {"firstName": user_data[x]["userName"].split()[0]},
                    "help": f"Number of photos by user {user_data[x]['userName'].split()[0]} ",
                }
            )
            metrics.append(
                {
                    "name": f"{self.config['metrics_prefix']}_server_stats_videos_by_users",
                    "value": user_data[x]["videos"],
                    "labels": {"firstName": user_data[x]["userName"].split()[0]},
                    "help": f"Number of photos by user {user_data[x]['userName'].split()[0]} ",
                }
            )
            metrics.append(
                {
                    "name": f"{self.config['metrics_prefix']}_server_stats_usage_by_users",
                    "value": (user_data[x]["usage"]),
                    "labels": {
                        "firstName": user_data[x]["userName"].split()[0],
                    },
                    "help": f"Number of photos by user {user_data[x]['userName'].split()[0]} ",
                }
            )

        metrics += [
            {
                "name": f"{self.config['metrics_prefix']}_server_stats_user_count",
                "value": user_count,
                "help": "number of users on the immich server",
            },
            {
                "name": f"{self.config['metrics_prefix']}_server_stats_photos_growth",
                "value": photos_growth_total,
                "help": "photos counter that is added or removed",
            },
            {
                "name": f"{self.config['metrics_prefix']}_server_stats_videos_growth",
                "value": videos_growth_total,
                "help": "videos counter that is added or removed",
            },
            {
                "name": f"{self.config['metrics_prefix']}_server_stats_usage_growth",
                "value": usage_growth_total,
                "help": "videos counter that is added or removed",
            },
        ]

        return metrics

    def get_immich_storage(self):
        try:
            endpoint_storage = "/storage"
            response_storage = self.request(endpoint_storage).json()
        except requests.exceptions.RequestException as e:
            logger.error("Couldn't get storage info: %s", e)

        return [
            {
                "name": f"{self.config['metrics_prefix']}_server_info_diskAvailable",
                "value": (response_storage["diskAvailableRaw"]),
                "help": "Available space on disk",
            },
            {
                "name": f"{self.config['metrics_prefix']}_server_info_totalDiskSize",
                "value": (response_storage["diskSizeRaw"]),
                "help": "total disk size",
                # "type": "counter"
            },
            {
                "name": f"{self.config['metrics_prefix']}_server_info_diskUse",
                "value": (response_storage["diskUseRaw"]),
                "help": "disk space in use",
                # "type": "counter"
            },
            {
                "name": f"{self.config['metrics_prefix']}_server_info_diskUsagePercentage",
                "value": (response_storage["diskUsagePercentage"]),
                "help": "disk usage in percent",
                # "type": "counter"
            },
        ]

    def get_immich_server_version_number(self):
        # Requesting immich_server_number serves two purposes.
        # As the name says it returns the version number
        #   1. get version the full server version number
        #   2. check if immich api key is correct
        # throwing connectionRefused exception usually means that immich isn't running

        server_version_endpoint = "/version"

        while True:
            try:
                response = self.request(server_version_endpoint).json()
            except requests.exceptions.RequestException:
                logger.error("Couldn't get server version")
                continue
            break

        server_version_number = (
            str(response["major"])
            + "."
            + str(response["minor"])
            + "."
            + str(response["patch"])
        )

        return [
            {
                "name": f"{self.config['metrics_prefix']}_server_info_version_number",
                "value": bool(server_version_number),
                "help": "server version number",
                "labels": {"version": server_version_number},
            }
        ]

    def get_system_stats(self):
        load_avg = os.getloadavg()
        virtual_mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1, percpu=False)
        return [
            {
                "name": f"{self.config['metrics_prefix']}_system_info_loadAverage",
                "value": load_avg[0],
                "help": "CPU Load average 1m",
                "labels": {"period": "1m"},
            },
            {
                "name": f"{self.config['metrics_prefix']}_system_info_loadAverage",
                "value": load_avg[1],
                "help": "CPU Load average 5m",
                "labels": {"period": "5m"},
            },
            {
                "name": f"{self.config['metrics_prefix']}_system_info_loadAverage",
                "value": load_avg[2],
                "help": "CPU Load average 15m",
                "labels": {"period": "15m"},
            },
            {
                "name": f"{self.config['metrics_prefix']}_system_info_memory",
                "value": virtual_mem[0],
                "help": "Virtual Memory - Total",
                "labels": {"type": "Total"},
            },
            {
                "name": f"{self.config['metrics_prefix']}_system_info_memory",
                "value": virtual_mem[1],
                "help": "Virtual Memory - Available",
                "labels": {"type": "Available"},
            },
            {
                "name": f"{self.config['metrics_prefix']}_system_info_memory",
                "value": virtual_mem[2],
                "help": "Virtual Memory - Percent",
                "labels": {"type": "Percent"},
            },
            {
                "name": f"{self.config['metrics_prefix']}_system_info_memory",
                "value": virtual_mem[3],
                "help": "Virtual Memory - Used",
                "labels": {"type": "Used"},
            },
            {
                "name": f"{self.config['metrics_prefix']}_system_info_memory",
                "value": virtual_mem[4],
                "help": "Virtual Memory - Free",
                "labels": {"type": "Free"},
            },
            {
                "name": f"{self.config['metrics_prefix']}_system_info_cpu_usage",
                "value": cpu,
                "help": "Representing the current system-wide CPU utilization as a percentage",
            },
        ]

    def combine_url(self, api_endpoint):
        prefix_url = "http://"
        base_url = self.config["immich_host"]
        base_url_port = self.config["immich_port"]
        base_api_endpoint = "/api/server"
        combined_url = (
            f"{prefix_url}{base_url}:{base_url_port}{base_api_endpoint}{api_endpoint}"
        )

        return combined_url


# test
class SignalHandler:
    def __init__(self):
        self.shutdown_count = 0

        # Register signal handler
        signal.signal(signal.SIGINT, self._on_signal_received)
        signal.signal(signal.SIGTERM, self._on_signal_received)

    def is_shutting_down(self):
        return self.shutdown_count > 0

    def _on_signal_received(self):
        if self.shutdown_count > 1:
            logger.warning("Forcibly killing exporter")
            sys.exit(1)
        logger.info("Exporter is shutting down")
        self.shutdown_count += 1


def get_config_value(key, default=""):
    input_path = os.environ.get("FILE__" + key, None)
    if input_path is not None:
        try:
            with open(input_path, "r") as input_file:
                return input_file.read().strip()
        except IOError as e:
            logger.error("Unable to read value for %s from %s: %s", key, input_path, e)

    return os.environ.get(key, default)


def check_server_up(immich_host, immich_port):
    counter = 0

    while True:
        counter = counter + 1
        try:
            requests.request(
                "GET",
                f"http://{immich_host}:{immich_port}/api/server/ping",
                headers={"Accept": "application/json"},
            )
        except requests.exceptions.RequestException:
            logger.error(
                "CONNECTION ERROR. Cannot reach immich at %s:%s. Is immich up and running?",
                immich_host,
                immich_port,
            )
            if 0 <= counter <= 60:
                time.sleep(1)
            elif 11 <= counter <= 300:
                time.sleep(15)
            elif counter > 300:
                time.sleep(60)
            continue
        break
    logger.info("Found immich up and running at %s:%s.", immich_host, immich_port)
    logger.info("Attempting to connect to immich")
    time.sleep(1)
    logger.info("Exporter 1.2.1")


def check_immich_api_key(immich_host, immich_port, immich_api_key):
    while True:
        try:
            requests.request(
                "GET",
                f"http://{immich_host}:{immich_port}/api/server/",
                headers={"Accept": "application/json", "x-api-key": immich_api_key},
            )
        except requests.exceptions.RequestException as e:
            logger.error("CONNECTION ERROR. Possible API key error")
            logger.error({e})
            time.sleep(3)
            continue
        logger.info("Success.")
        break


def main():
    # Init logger so it can be used
    log_handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime) %(levelname) %(message)", datefmt="%Y-%m-%d %H:%M:%S"
    )
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)
    logger.setLevel("INFO")  # default until config is loaded

    config = {
        "immich_host": get_config_value("IMMICH_HOST", ""),
        "immich_port": get_config_value("IMMICH_PORT", ""),
        "token": get_config_value("IMMICH_API_TOKEN", ""),
        "exporter_port": int(get_config_value("EXPORTER_PORT", "8000")),
        "log_level": get_config_value("EXPORTER_LOG_LEVEL", "INFO"),
        "metrics_prefix": get_config_value("METRICS_PREFIX", "immich"),
    }
    # set level once config has been loaded
    logger.setLevel(config["log_level"])

    # Register signal handler
    signal_handler = SignalHandler()

    if not config["immich_host"]:
        logger.error("No host specified, please set IMMICH_HOST environment variable")
        sys.exit(1)
    if not config["immich_port"]:
        logger.error("No host specified, please set IMMICH_PORT environment variable")
        sys.exit(1)
    if not config["token"]:
        logger.error(
            "No token specified, please set IMMICH_API_TOKEN environment variable"
        )
        sys.exit(1)

    # Register our custom collector
    logger.info("Exporter is starting up")

    check_server_up(config["immich_host"], config["immich_port"])
    check_immich_api_key(config["immich_host"], config["immich_port"], config["token"])
    REGISTRY.register(ImmichMetricsCollector(config))

    # Start server
    start_http_server(config["exporter_port"])

    logger.info("Exporter listening on port %s", config["exporter_port"])

    while not signal_handler.is_shutting_down():
        time.sleep(1)

    logger.info("Exporter has shutdown")
