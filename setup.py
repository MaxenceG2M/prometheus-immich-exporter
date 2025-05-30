from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

version = '1.2.1'

setup(
    name='prometheus-immich-exporter',
    packages=['immich_exporter'],
    version=version,
    long_description=long_description,
    long_description_content_type="text/markdown",
    description='Prometheus exporter for immich',
   # forked from:
   # author='friendlyFriend4000',
   # author_email='mailto:127642970+friendlyFriend4000@users.noreply.github.com',
   # url='https://github.com/friendlyFriend4000/prometheus-immich-exporter',
    keywords=['prometheus', 'immich'],
    classifiers=[],
    python_requires='>=3',
    entry_points={
        'console_scripts': [
            'immich_exporter=immich_exporter.exporter:main',
        ]
    }
)
