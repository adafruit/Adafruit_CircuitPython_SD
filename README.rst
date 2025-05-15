
Introduction
============

.. image:: https://readthedocs.org/projects/adafruit-circuitpython-sd/badge/?version=latest
    :target: https://docs.circuitpython.org/projects/sd/en/latest/
    :alt: Documentation Status

.. image:: https://raw.githubusercontent.com/adafruit/Adafruit_CircuitPython_Bundle/main/badges/adafruit_discord.svg
    :target: https://adafru.it/discord
    :alt: Discord

.. image:: https://github.com/adafruit/Adafruit_CircuitPython_SD/workflows/Build%20CI/badge.svg
    :target: https://github.com/adafruit/Adafruit_CircuitPython_SD/actions/
    :alt: Build Status

.. image:: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
    :target: https://github.com/astral-sh/ruff
    :alt: Code Style: Ruff

CircuitPython driver for SD cards. This implements the basic reading and writing
block functionality needed to mount an SD card using `storage.VfsFat`.

Dependencies
=============
This driver depends on:

* `Adafruit CircuitPython 2.0.0+ <https://github.com/adafruit/circuitpython>`_
* `Bus Device <https://github.com/adafruit/Adafruit_CircuitPython_BusDevice>`_

Please ensure all dependencies are available on the CircuitPython filesystem.
This is easily achieved by downloading
`the Adafruit library and driver bundle <https://github.com/adafruit/Adafruit_CircuitPython_Bundle>`_.

Usage Example
=============

Mounting a filesystem on an SD card so that its available through the normal Python
ways is easy.

Below is an example for the Feather M0 Adalogger. Most of this will stay the same
across different boards with the exception of the pins for the SPI and chip
select (cs) connections.

.. code-block:: python

    import adafruit_sdcard
    import busio
    import digitalio
    import board
    import storage

    # Connect to the card and mount the filesystem.
    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
    cs = digitalio.DigitalInOut(board.SD_CS)
    sdcard = adafruit_sdcard.SDCard(spi, cs)
    vfs = storage.VfsFat(sdcard)
    storage.mount(vfs, "/sd")

    # Use the filesystem as normal.
    with open("/sd/test.txt", "w") as f:
        f.write("Hello world\n")

Sharing the SPI bus with other devices
======================================

.. important::
    If the same SPI bus is shared with other peripherals, it is important that
    the SD card be initialized before accessing any other peripheral on the bus.
    Failure to do so can prevent the SD card from being recognized until it is
    powered off or re-inserted.


Documentation
=============

API documentation for this library can be found on `Read the Docs <https://docs.circuitpython.org/projects/sd/en/latest/>`_.

For information on building library documentation, please check out `this guide <https://learn.adafruit.com/creating-and-sharing-a-circuitpython-library/sharing-our-docs-on-readthedocs#sphinx-5-1>`_.

Contributing
============

Contributions are welcome! Please read our `Code of Conduct
<https://github.com/adafruit/Adafruit_CircuitPython_sdcard/blob/main/CODE_OF_CONDUCT.md>`_
before contributing to help this project stay welcoming.
