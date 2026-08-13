#!/usr/bin/env python3
#
# Copyright 2025 Ettus Research, a National Instruments Brand
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""
Pure Python implementation of Aurora Block Controller

This module provides a Python-only implementation of the Aurora block controller
that doesn't require the compiled rfnoc_oot_blocks module. It accesses the Aurora
block registers directly through the UHD RFNoC noc_block_base interface.

This is intended for use on platforms (e.g., Windows) where building the OOT
module is not feasible, but you still need to control Aurora blocks.

Usage:
    try:
        from rfnoc_oot_blocks import AuroraBlockControl, channel_stop_policy
    except ImportError:
        from aurora_block_control_python import AuroraBlockControl, channel_stop_policy
"""

import uhd.rfnoc


# Constants matching the C++ implementation
AURORA_BLOCK_ID = 0xA404A000


class channel_stop_policy:
    """Enum for Aurora channel stop policy"""

    DROP = 0  # Drop all packets from Aurora until we start
    BUFFER = 1  # Packets are held back until we start


class aurora_status_struct:
    """Aurora status structure matching C++ status_struct"""

    def __init__(self):
        self.lane_status = []
        self.link_status = False
        self.aurora_hard_error_status = False
        self.aurora_soft_error_status = False
        self.aurora_mmcm_lock_status = False
        self.aurora_gt_pll_lock_status = False


class AuroraBlockControl:
    """
    Pure Python Aurora Block Controller

    This class provides the same API as the C++ AuroraBlockControl but
    implements it using direct register access through UHD's Python bindings.
    """

    # Class constant for ALL_CHANS (matches C++ size_t(~0))
    ALL_CHANS = 0xFFFFFFFFFFFFFFFF

    # Register addresses and bit positions (from aurora_block_control.cpp)
    REG_COMPAT_ADDR = 0x0
    REG_CORE_CONFIG_ADDR = 0x4
    REG_NUM_CORES_POS = 0
    REG_NUM_CORES_MASK = 0xFF
    REG_NUM_CHAN_POS = 16
    REG_NUM_CHAN_MASK = 0xFF
    REG_CORE_STATUS_ADDR = 0x8
    REG_LANE_STATUS_POS = 0
    REG_LANE_STATUS_MASK = 0xF
    REG_LANE_STATUS_LEN = 4
    REG_LINK_STATUS_POS = 4
    REG_HARD_ERR_POS = 8
    REG_SOFT_ERR_POS = 9
    REG_MMCM_LOCK_POS = 12
    REG_PLL_LOCK_POS = 13
    REG_CORE_RESET_ADDR = 0xC
    REG_AURORA_RESET_POS = 0
    REG_TX_DATAPATH_RESET_POS = 1
    REG_RX_DATAPATH_RESET_POS = 2
    REG_CORE_FC_PAUSE_ADDR = 0x10
    REG_PAUSE_COUNT_POS = 0
    REG_PAUSE_COUNT_MASK = 0xFF
    REG_CORE_FC_THRESHOLD_ADDR = 0x14
    REG_PAUSE_THRESH_POS = 0
    REG_PAUSE_THRESH_MASK = 0xFF
    REG_RESUME_THRESH_POS = 16
    REG_RESUME_THRESH_MASK = 0xFF
    REG_CORE_TX_PKT_CTR_ADDR = 0x18
    REG_CORE_RX_PKT_CTR_ADDR = 0x1C
    REG_CORE_OVERFLOW_CTR_ADDR = 0x20
    REG_CORE_CRC_ERR_CTR_ADDR = 0x24
    REG_CHAN_TX_CTRL_ADDR = 0x0
    REG_CHAN_TX_CTRL_MASK = 0x3
    REG_CHAN_TX_START_POS = 0
    REG_CHAN_TX_STOP_POS = 1
    REG_CHAN_TS_LOW_ADDR = 0x4
    REG_CHAN_TS_LOW_MASK = 0xFFFFFFFF
    REG_CHAN_TS_HIGH_ADDR = 0x8
    REG_CHAN_TS_HIGH_MASK = 0xFFFFFFFF
    REG_CHAN_STOP_POLICY_ADDR = 0xC
    REG_CHAN_STOP_POLICY_MASK = 0x1
    REG_CHAN_TS_QUEUE_STS_ADDR = 0x10
    REG_CHAN_TS_QUEUE_STS_MASK = 0xFFFFFFFF
    REG_TS_FULLNESS_POS = 0
    REG_TS_FULLNESS_MASK = 0xFFFF
    REG_TS_SIZE_POS = 16
    REG_TS_SIZE_MASK = 0xFFFF
    REG_CHAN_TS_QUEUE_CTRL_ADDR = 0x14
    REG_CHAN_TS_QUEUE_CTRL_MASK = 0x00000001

    channel_reg_size = 1 << 6  # 64 bytes per channel
    core_reg_size = 1 << 11  # 2048 bytes per core

    def __init__(self, block):
        """
        Initialize Aurora block controller

        Args:
            block: uhd.rfnoc.NocBlock instance (the raw Aurora block from graph.get_block())
        """
        if not isinstance(block, uhd.rfnoc.NocBlock):
            raise TypeError("block must be a uhd.rfnoc.NocBlock instance")

        self._block = block

        # Verify this is an Aurora block by checking the NOC ID
        block_id = self._block.get_noc_id()
        if block_id != AURORA_BLOCK_ID:
            raise ValueError(
                f"Block ID 0x{block_id:08X} does not match Aurora block ID 0x{AURORA_BLOCK_ID:08X}"
            )

        # Read configuration
        config_reg = self._peek32(self.REG_CORE_CONFIG_ADDR)
        self._num_cores = (config_reg >> self.REG_NUM_CORES_POS) & self.REG_NUM_CORES_MASK
        self._num_channels = (config_reg >> self.REG_NUM_CHAN_POS) & self.REG_NUM_CHAN_MASK

        self._channels = list(range(self._num_channels))

        # Perform initial reset
        self._reset()

    def _peek32(self, addr):
        """Read a 32-bit register"""
        return self._block.peek32(addr)

    def _poke32(self, addr, data):
        """Write a 32-bit register"""
        self._block.poke32(addr, data)

    def _peek32_channel_reg(self, channel, addr):
        """Read a channel-specific 32-bit register"""
        return self._peek32(addr + ((channel + 1) * self.channel_reg_size))

    def _poke32_channel_reg(self, channel, addr, data):
        """Write a channel-specific 32-bit register"""
        self._poke32(addr + ((channel + 1) * self.channel_reg_size), data)

    def _assert_channel_param(self, channel):
        """Validate channel parameter"""
        if channel >= self._num_channels:
            raise ValueError(
                f"channel {channel} is invalid, Aurora block has only {self._num_channels} channels"
            )

    def _reset(self):
        """Internal reset function"""
        self._poke32(
            self.REG_CORE_RESET_ADDR,
            (1 << self.REG_AURORA_RESET_POS)
            | (1 << self.REG_TX_DATAPATH_RESET_POS)
            | (1 << self.REG_RX_DATAPATH_RESET_POS),
        )
        for channel in self._channels:
            self._poke32_channel_reg(channel, self.REG_CHAN_TS_QUEUE_CTRL_ADDR, 1)

    def _tx_datapath_enable(self, channel, enable):
        """Internal TX datapath enable for a single channel"""
        if enable:
            self._poke32_channel_reg(
                channel, self.REG_CHAN_TX_CTRL_ADDR, 1 << self.REG_CHAN_TX_START_POS
            )
        else:
            self._poke32_channel_reg(
                channel, self.REG_CHAN_TX_CTRL_ADDR, 1 << self.REG_CHAN_TX_STOP_POS
            )

    # Public API methods

    def get_status(self):
        """
        Query the aurora core status (all status parameters)

        Returns:
            aurora_status_struct: General core status
        """
        raw_value = self._peek32(self.REG_CORE_STATUS_ADDR)
        status = aurora_status_struct()

        for lane in range(self.REG_LANE_STATUS_LEN):
            status.lane_status.append(bool((raw_value >> (self.REG_LANE_STATUS_POS + lane)) & 1))

        status.link_status = bool((raw_value >> self.REG_LINK_STATUS_POS) & 1)
        status.aurora_hard_error_status = bool((raw_value >> self.REG_HARD_ERR_POS) & 1)
        status.aurora_soft_error_status = bool((raw_value >> self.REG_SOFT_ERR_POS) & 1)
        status.aurora_mmcm_lock_status = bool((raw_value >> self.REG_MMCM_LOCK_POS) & 1)
        status.aurora_gt_pll_lock_status = bool((raw_value >> self.REG_PLL_LOCK_POS) & 1)

        return status

    def get_link_status(self):
        """
        Query the aurora core status (only the link status)

        Returns:
            bool: Aurora link status
        """
        return self.get_status().link_status

    def get_lane_status(self, channel=None):
        """
        Query the aurora core status (only the lane status)

        Args:
            channel: The channel to query (optional). If None, returns all lane statuses.

        Returns:
            bool or list[bool]: Aurora lane status for channel, or list of all lane statuses
        """
        if channel is None:
            return [self.get_status().lane_status[ch] for ch in self._channels]
        else:
            self._assert_channel_param(channel)
            return self.get_status().lane_status[channel]

    def get_fc_pause_count(self):
        """
        Gets the Aurora native flow control (NFC) parameter pause count

        Returns:
            int: pause count in number of cycles
        """
        return (
            self._peek32(self.REG_CORE_FC_PAUSE_ADDR) >> self.REG_PAUSE_COUNT_POS
        ) & self.REG_PAUSE_COUNT_MASK

    def set_fc_pause_count(self, pause_count):
        """
        Sets the Aurora native flow control (NFC) parameter pause count

        Args:
            pause_count (int): pause count in number of cycles
        """
        if 0 < pause_count < 10:
            raise ValueError("Invalid pause count value")
        self._poke32(self.REG_CORE_FC_PAUSE_ADDR, pause_count << self.REG_PAUSE_COUNT_POS)

    def get_fc_pause_threshold(self):
        """
        Gets the Aurora native flow control (NFC) parameter pause threshold

        Returns:
            int: pause threshold in number of Aurora data words
        """
        return (
            self._peek32(self.REG_CORE_FC_THRESHOLD_ADDR) >> self.REG_PAUSE_THRESH_POS
        ) & self.REG_PAUSE_THRESH_MASK

    def set_fc_pause_threshold(self, pause_threshold):
        """
        Sets the Aurora native flow control (NFC) parameter pause threshold

        Args:
            pause_threshold (int): pause threshold in number of Aurora data words
        """
        other_bits = self._peek32(self.REG_CORE_FC_THRESHOLD_ADDR) & ~(
            self.REG_PAUSE_THRESH_MASK << self.REG_PAUSE_THRESH_POS
        )
        own_bits = pause_threshold << self.REG_PAUSE_THRESH_POS
        self._poke32(self.REG_CORE_FC_THRESHOLD_ADDR, other_bits | own_bits)

    def get_fc_resume_threshold(self):
        """
        Gets the Aurora native flow control (NFC) parameter resume threshold

        Returns:
            int: resume threshold in number of Aurora data words
        """
        return (
            self._peek32(self.REG_CORE_FC_THRESHOLD_ADDR) >> self.REG_RESUME_THRESH_POS
        ) & self.REG_RESUME_THRESH_MASK

    def set_fc_resume_threshold(self, resume_threshold):
        """
        Sets the Aurora native flow control (NFC) parameter resume threshold

        Args:
            resume_threshold (int): resume threshold in number of Aurora data words
        """
        existing_bits = self._peek32(self.REG_CORE_FC_THRESHOLD_ADDR) & ~(
            self.REG_RESUME_THRESH_MASK << self.REG_RESUME_THRESH_POS
        )
        own_bits = resume_threshold << self.REG_RESUME_THRESH_POS
        self._poke32(self.REG_CORE_FC_THRESHOLD_ADDR, existing_bits | own_bits)

    def get_aurora_rx_packet_counter(self):
        """
        Gets the number of Aurora packets received

        Returns:
            int: Number of Aurora packets received (Aurora to RFNoC)
        """
        return self._peek32(self.REG_CORE_RX_PKT_CTR_ADDR)

    def get_aurora_tx_packet_counter(self):
        """
        Gets the number of Aurora packets transmitted

        Returns:
            int: Number of Aurora packets transmitted (RFNoC to Aurora)
        """
        return self._peek32(self.REG_CORE_TX_PKT_CTR_ADDR)

    def get_aurora_overflow_counter(self):
        """
        Gets the number of Aurora data words dropped due to buffer overflow

        Returns:
            int: number of Aurora data words dropped
        """
        return self._peek32(self.REG_CORE_OVERFLOW_CTR_ADDR)

    def get_aurora_crc_error_counter(self):
        """
        Gets the number of CRC errors detected

        Returns:
            int: number of Aurora packets dropped due to CRC errors
        """
        return self._peek32(self.REG_CORE_CRC_ERR_CTR_ADDR)

    def tx_datapath_enable(self, enable, channel=None):
        """
        Controls the start and stop of the TX datapath

        Args:
            enable (bool): Enable (True) or disable (False) the TX data path
            channel (int, optional): Channel number. Defaults to ALL_CHANS.
        """
        if channel is None:
            channel = self.ALL_CHANS

        if channel == self.ALL_CHANS:
            for ch in self._channels:
                self._tx_datapath_enable(ch, enable)
        else:
            self._assert_channel_param(channel)
            self._tx_datapath_enable(channel, enable)

    def tx_datapath_enqueue_timestamp(self, timestamp, channel=None):
        """
        Sets the next TX timestamp to be used for the next start of transmission

        Args:
            timestamp (int): The timestamp to use
            channel (int, optional): Channel number. Defaults to ALL_CHANS.
        """
        if channel is None:
            channel = self.ALL_CHANS

        if channel == self.ALL_CHANS:
            for ch in self._channels:
                self.tx_datapath_enqueue_timestamp(timestamp, ch)
        else:
            self._assert_channel_param(channel)
            self._poke32_channel_reg(
                channel, self.REG_CHAN_TS_LOW_ADDR, timestamp & self.REG_CHAN_TS_LOW_MASK
            )
            self._poke32_channel_reg(
                channel, self.REG_CHAN_TS_HIGH_ADDR, (timestamp >> 32) & self.REG_CHAN_TS_HIGH_MASK
            )

    def get_channel_stop_policy(self, channel=None):
        """
        Gets the behavior of the TX datapath

        Args:
            channel (int, optional): Channel number. If None, returns list for all channels.

        Returns:
            int or list[int]: The channel stop policy (channel_stop_policy.DROP or .BUFFER)
        """
        if channel is None:
            return [self.get_channel_stop_policy(ch) for ch in self._channels]
        else:
            self._assert_channel_param(channel)
            ret_value = (
                self._peek32_channel_reg(channel, self.REG_CHAN_STOP_POLICY_ADDR)
                & self.REG_CHAN_STOP_POLICY_MASK
            )
            return ret_value

    def set_channel_stop_policy(self, stop_policy, channel=None):
        """
        Sets the behavior of the TX datapath

        Args:
            stop_policy (int): The channel stop policy (channel_stop_policy.DROP or .BUFFER)
            channel (int, optional): Channel number. Defaults to ALL_CHANS.
        """
        if channel is None:
            channel = self.ALL_CHANS

        if channel == self.ALL_CHANS:
            for ch in self._channels:
                self.set_channel_stop_policy(stop_policy, ch)
        else:
            self._assert_channel_param(channel)
            self._poke32_channel_reg(channel, self.REG_CHAN_STOP_POLICY_ADDR, stop_policy)

    def get_timestamp_queue_fullness(self, channel=None):
        """
        Gets the status of the timestamp queue

        Args:
            channel (int, optional): Channel number. If None, returns list for all channels.

        Returns:
            int or list[int]: Number of timestamp entries in the queue
        """
        if channel is None:
            return [self.get_timestamp_queue_fullness(ch) for ch in self._channels]
        else:
            self._assert_channel_param(channel)
            return (
                self._peek32_channel_reg(channel, self.REG_CHAN_TS_QUEUE_STS_ADDR)
                >> self.REG_TS_FULLNESS_POS
            ) & self.REG_TS_FULLNESS_MASK

    def get_timestamp_queue_size(self, channel=None):
        """
        Gets the size of the timestamp queue

        Args:
            channel (int, optional): Channel number. If None, returns list for all channels.

        Returns:
            int or list[int]: Timestamp queue size
        """
        if channel is None:
            return [self.get_timestamp_queue_size(ch) for ch in self._channels]
        else:
            self._assert_channel_param(channel)
            return (
                self._peek32_channel_reg(channel, self.REG_CHAN_TS_QUEUE_STS_ADDR)
                >> self.REG_TS_SIZE_POS
            ) & self.REG_TS_SIZE_MASK

    def get_num_cores(self):
        """
        Gets the number of aurora cores in the FPGA

        Returns:
            int: Number of aurora cores
        """
        return self._num_cores

    def get_num_channels(self):
        """
        Gets the number of channels per aurora core

        Returns:
            int: Number of channels
        """
        return self._num_channels

    def get_channels(self):
        """
        Gets a vector containing all channel indices

        Returns:
            list[int]: Vector of channel indices
        """
        return self._channels.copy()

    def reset_tx(self):
        """Resets the TX datapath only"""
        self._poke32(self.REG_CORE_RESET_ADDR, 1 << self.REG_TX_DATAPATH_RESET_POS)

    def reset(self):
        """Resets the Aurora IP, the TX datapath, and the RX datapath"""
        self._reset()

    def get_unique_id(self):
        """
        Get the unique block ID (for compatibility with examples)

        Returns:
            str: Unique block ID
        """
        return self._block.get_unique_id()
