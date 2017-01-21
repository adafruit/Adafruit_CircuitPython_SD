# The MIT License (MIT)
#
# Copyright (c) 2014-2016 Damien George, Peter Hinch and Radomir Dopieralski
# Copyright (c) 2017 Scott Shawcroft for Adafruit Industries
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
"""
`adafruit_sdcard`
====================================================

CircuitPython driver for SD cards using SPI bus.

Requires an SPI bus and a CS pin.  Provides readblocks and writeblocks
methods so the device can be mounted as a filesystem.

Example usage on pyboard:

    import nativeio
    import filesystem
    import adafruit_sdcard
    import os
    import board

    spi = nativeio.SPI(SCK, MOSI, MISO)
    sd = adafruit_sdcard.SDCard(spi, board.SD_CS)
    filesystem.mount(sd, '/sd2')
    os.listdir('/')

* Author(s): Scott Shawcroft
"""

from micropython import const
from adafruit_bus_device import spi_device
import time

_CMD_TIMEOUT = const(200)

_R1_IDLE_STATE = const(1 << 0)
#R1_ERASE_RESET = const(1 << 1)
_R1_ILLEGAL_COMMAND = const(1 << 2)
#R1_COM_CRC_ERROR = const(1 << 3)
#R1_ERASE_SEQUENCE_ERROR = const(1 << 4)
#R1_ADDRESS_ERROR = const(1 << 5)
#R1_PARAMETER_ERROR = const(1 << 6)
_TOKEN_CMD25 = const(0xfc)
_TOKEN_STOP_TRAN = const(0xfd)
_TOKEN_DATA = const(0xfe)

class SDCard:
    def __init__(self, spi, cs):
        # This is the init baudrate. We create a second device for high speed.
        self.spi = spi_device.SPIDevice(spi, cs, baudrate=250000, extra_clocks=8)

        self.cmdbuf = bytearray(6)
        self.single_byte = bytearray(1)

        # Card is byte addressing, set to 1 if addresses are per block
        self.cdv = 512

        # initialise the card
        self.init_card()

    def clock_card(self, cycles=8):
        "Clock the bus a minimum of `cycles` with the chip select high."
        while not self.spi.spi.try_lock():
            pass
        self.spi.spi.configure(baudrate=self.spi.baudrate)
        self.spi.chip_select.value = True

        self.single_byte[0] = 0xff
        for i in range(cycles // 8 + 1):
            self.spi.spi.write(self.single_byte)
        self.spi.spi.unlock()

    def init_card(self):
        # clock card at least cycles with cs high
        self.clock_card(80)

        # CMD0: init card; should return _R1_IDLE_STATE (allow 5 attempts)
        for _ in range(5):
            if self.cmd(0, 0, 0x95) == _R1_IDLE_STATE:
                break
        else:
            raise OSError("no SD card")

        # CMD8: determine card version
        r = self.cmd(8, 0x01aa, 0x87, 4)
        if r == _R1_IDLE_STATE:
            self.init_card_v2()
        elif r == (_R1_IDLE_STATE | _R1_ILLEGAL_COMMAND):
            self.init_card_v1()
        else:
            raise OSError("couldn't determine SD card version")

        # get the number of sectors
        # CMD9: response R2 (R1 byte + 16-byte block read)
        csd = bytearray(16)
        if self.cmd(9, 0, 0, response_buf=csd) != 0:
            raise OSError("no response from SD card")
        #self.readinto(csd)
        csd_version = (csd[0] & 0xc0) >> 6
        if csd_version >= 2:
            raise OSError("SD card CSD format not supported")
        print(csd)
        if csd_version == 1:
            self.sectors = ((csd[8] << 8 | csd[9]) + 1) * 1024
        else:
            block_length = 2 ** (csd[5] & 0xf)
            c_size = ((csd[6] & 0x3) << 10) | (csd[7] << 2) | ((csd[8] & 0xc) >> 6)
            mult = 2 ** (((csd[9] & 0x3) << 1 | (csd[10] & 0x80) >> 7) + 2)
            print(mult, block_length)
            self.sectors = block_length // 512 * mult * (c_size + 1)
        print('sectors', self.sectors)

        # CMD16: set block length to 512 bytes
        if self.cmd(16, 512, 0) != 0:
            raise OSError("can't set 512 block size")

        # set to high data rate now that it's initialised
        self.spi = spi_device.SPIDevice(self.spi.spi, self.spi.chip_select, baudrate=1320000, extra_clocks=8)

    def init_card_v1(self):
        for i in range(_CMD_TIMEOUT):
            self.cmd(55, 0, 0)
            if self.cmd(41, 0, 0) == 0:
                print("[SDCard] v1 card")
                return
        raise OSError("timeout waiting for v1 card")

    def init_card_v2(self):
        for i in range(_CMD_TIMEOUT):
            time.sleep(.050)
            self.cmd(58, 0, 0, 4)
            self.cmd(55, 0, 0)
            if self.block_cmd(41, 0x200000, 0) == 0:
                self.cmd(58, 0, 0, 4)
                self.cdv = 1
                print("[SDCard] v2 card")
                return
        raise OSError("timeout waiting for v2 card")

    def wait_for_ready(self, spi, timeout=0.3):
        start_time = time.monotonic()
        self.single_byte[0] = 0x00
        while time.monotonic() - start_time < timeout and self.single_byte[0] != 0xff:
            spi.readinto(self.single_byte, write_value=0xff)

    def cmd(self, cmd, arg, crc, final=0, response_buf=None):
        # create and send the command
        buf = self.cmdbuf
        buf[0] = 0x40 | cmd
        buf[1] = arg >> 24
        buf[2] = arg >> 16
        buf[3] = arg >> 8
        buf[4] = arg
        buf[5] = crc

        with self.spi as spi:
            self.wait_for_ready(spi)

            spi.write(buf)

            # wait for the response (response[7] == 0)
            for i in range(_CMD_TIMEOUT):
                spi.readinto(buf, end=1, write_value=0xff)
                if not (buf[0] & 0x80):
                    # this could be a big-endian integer that we are getting here
                    buf[1] = 0xff
                    for _ in range(final):
                        spi.write(buf, start=1, end=2)
                    if response_buf:
                        # Wait for the start block byte
                        while buf[1] != 0xfe:
                            spi.readinto(buf, start=1, end=2, write_value=0xff)
                        spi.readinto(response_buf, write_value=0xff)

                        # Read the checksum
                        spi.readinto(buf, start=1, end=3, write_value=0xff)
                    return buf[0]
        return -1

    def block_cmd(self, cmd, block, crc):
        if self.cdv == 1:
            self.cmd(cmd, block, crc)
            return

        # create and send the command
        buf = self.cmdbuf
        buf[0] = 0x40 | cmd
        # We address by byte because cdv is 512. Instead of multiplying, shift
        # the data to the correct spot so that we don't risk creating a long
        # int.
        buf[1] = (block >> 15) & 0xff
        buf[2] = (block >> 7) & 0xff
        buf[3] = (block << 1) & 0xff
        buf[4] = 0
        buf[5] = crc

        with self.spi as spi:
            spi.write(buf)

            # wait for the response (response[7] == 0)
            for i in range(_CMD_TIMEOUT):
                spi.readinto(buf, end=1, write_value=0xff)
                if not (buf[0] & 0x80):
                    return buf[0]
        return -1

    def cmd_nodata(self, cmd):
        buf = self.cmdbuf
        buf[0] = cmd
        buf[1] = 0xff

        with self.spi as spi:
            spi.write(buf, end=2)
            for _ in range(_CMD_TIMEOUT):
                spi.readinto(buf, end=1, write_value=0xff)
                if buf[0] == 0xff:
                    return 0    # OK
        return 1 # timeout

    def readinto(self, buf, start=0, end=None):
        if end is None:
            end = len(buf)
        with self.spi as spi:
            # read until start byte (0xfe)
            buf[start] = 0xff #b usy
            while buf[start] == 0xff:
                spi.readinto(buf, start=start, end=start+1, write_value=0xff)

            # If the first block isn't the start block byte (0xfe) then the card
            # was ready and this is the first byte. So, read one less by
            # shifting the start.
            if buf[start] != 0xfe:
                start += 1

            spi.readinto(buf, start=start, end=end, write_value=0xff)

            # read checksum and throw it away
            spi.readinto(self.cmdbuf, end=2, write_value=0xff)

    def write(self, token, buf, start=0, end=None):
        cmd = self.cmdbuf
        if end is None:
            end = len(buf)
        with self.spi as spi:
            # send: start of block, data, checksum
            buf[0] = token
            spi.write(cmd, end=1)
            spi.write(buf, start=start, end=end)
            cmd[0] = 0xff
            cmd[1] = 0xff
            spi.write(cmd, end=2)

            # check the response
            spi.read(cmd, end=1)
            if (cmd[0] & 0x1f) != 0x05:
                # TODO(tannewt): Is this an error?
                return

            # wait for write to finish
            spi.readinto(cmd, end=1, write_value=0xff)
            while cmd[0] == 0:
                spi.readinto(cmd, end=1, write_value=0xff)

    def write_token(self, token):
        cmd = self.cmdbuf
        with self.spi as spi:
            cmd[0] = token
            cmd[1] = 0xff
            spi.write(cmd, end=2)
            # wait for write to finish
            spi.readinto(buf, end=1, write_value=0xff)
            while buf[0] == 0:
                spi.readinto(buf, end=1, write_value=0xff)

    def count(self):
        return self.sectors

    def readblocks(self, block_num, buf):
        nblocks, err = divmod(len(buf), 512)
        assert nblocks and not err, 'Buffer length is invalid'
        if nblocks == 1:
            # CMD17: set read address for single block
            if self.block_cmd(17, block_num, 0) != 0:
                return 1
            # receive the data
            self.readinto(buf)
        else:
            # CMD18: set read address for multiple blocks
            if self.block_cmd(18, block_num, 0) != 0:
                return 1
            offset = 0
            while nblocks:
                self.readinto(buf, start=offset, end=(offset + 512))
                offset += 512
                nblocks -= 1
            return self.cmd_nodata(b'\x0c') # cmd 12
        return 0

    def writeblocks(self, block_num, buf):
        nblocks, err = divmod(len(buf), 512)
        assert nblocks and not err, 'Buffer length is invalid'
        if nblocks == 1:
            # CMD24: set write address for single block
            if self.block_cmd(24, block_num, 0) != 0:
                return 1

            # send the data
            self.write(_TOKEN_DATA, buf)
        else:
            # CMD25: set write address for first block
            if self.block_cmd(25, block_num, 0) != 0:
                return 1
            # send the data
            offset = 0
            while nblocks:
                self.write(_TOKEN_CMD25, mv, start=offset, end=(offset + 512))
                offset += 512
                nblocks -= 1
            self.write_token(_TOKEN_STOP_TRAN)
        return 0
