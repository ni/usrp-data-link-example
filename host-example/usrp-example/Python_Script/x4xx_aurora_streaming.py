#!/usr/bin/env python3
#
# Copyright 2025 Ettus Research, a National Instruments Brand
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""
X420 Aurora Streaming Example

This example configures an X420 to stream data between the radio and Aurora
ports. It supports streaming in TX direction (Aurora → Radio), RX direction
(Radio → Aurora), or both simultaneously.

The example does the following:
1. Configures the RFNoC topology (Radio ↔ Aurora connections)
2. Waits for Aurora link(s) to come up
3. Waits for user to press Enter
4. Starts streaming in the specified direction(s)
5. Monitors and displays status (link, packet counters, errors)
6. Cleanly shuts down on Ctrl+C
"""

import collections
import time
import uhd.rfnoc
import uhd

try:
    from rfnoc_oot_blocks import AuroraBlockControl, channel_stop_policy
except ImportError:
    from aurora_block_control_python import AuroraBlockControl, channel_stop_policy


# Named tuple to hold RFNoC graph settings
GraphSettings = collections.namedtuple(
    "GraphSettings", ["tx_radios", "rx_radios", "tx_chans", "rx_chans"]
)

# Named tuple to hold Aurora Settings
TxAuroraSettings = collections.namedtuple(
    "TxAuroraSettings", ["policy", "pause_count", "pause_threshold", "resume_threshold"]
)

# Aurora block NOC ID
AURORA_BLOCK_ID = 0xA404A000

class ExampleSession:
    """ExampleSession class to hold USRP device and graph information."""

    def __init__(self, args):
        """Initialize the ExampleSession with the given arguments."""
        self.args = args
        self.graph = uhd.rfnoc.RfnocGraph(args)
        self.radio_blocks = {}
        self.radio_ctrls = {}
        self.aurora_blocks = {}

    def __del__(self):
        """Destructor to clean up the ExampleSession."""
        self.graph = None

    def setup_graph(self, graph_settings):
        """Set up RFNoC graph with Radio and Aurora blocks.

        This method discovers and connects Radio and Aurora blocks.

        Args:
            graph_settings: GraphSettings named tuple with rx/tx radio and channel info
        """
        num_channels = len(graph_settings.tx_radios)
        if num_channels < 1:
            raise RuntimeError("At least one channel must be configured")
        if len(graph_settings.rx_radios) != num_channels:
            raise RuntimeError("tx_radios and rx_radios must have the same length")
        if len(graph_settings.tx_chans) != num_channels:
            raise RuntimeError("tx_chans length must match tx_radios length")
        if len(graph_settings.rx_chans) != num_channels:
            raise RuntimeError("rx_chans length must match rx_radios length")

        for idx in range(num_channels):
            tx_radio = graph_settings.tx_radios[idx]
            rx_radio = graph_settings.rx_radios[idx]
            tx_chan = graph_settings.tx_chans[idx]
            rx_chan = graph_settings.rx_chans[idx]

            channel = tx_radio

            if tx_radio != rx_radio:
                raise RuntimeError(
                    f"Channel {channel} maps to different TX/RX radios ({tx_radio}, {rx_radio})"
                )
            if tx_chan != rx_chan:
                raise RuntimeError(
                    f"Channel {channel} TX/RX channel mismatch ({tx_chan}, {rx_chan})"
                )

            radio_block = None
            for block_id in [f"0/Radio#{tx_radio}", f"Radio#{tx_radio}"]:
                try:
                    radio_block = self.graph.get_block(block_id)
                    break
                except (RuntimeError, LookupError):
                    continue

            if radio_block is None:
                raise RuntimeError(f"Could not find Radio block for radio {tx_radio}")

            _, aurora_block = find_aurora_block(self.graph, channel)

            self.radio_blocks[channel] = radio_block
            self.radio_ctrls[channel] = uhd.rfnoc.RadioControl(radio_block)
            self.aurora_blocks[channel] = AuroraBlockControl(aurora_block)

            connect_blocks(
                self.graph,
                radio_block.get_unique_id(),
                aurora_block.get_unique_id(),
                radio_port=tx_chan,
                aurora_port=0,
            )

        self.graph.commit()


def check_session(session: any) -> None:
    """Check if session is a valid ExampleSession object."""
    if not isinstance(session, ExampleSession):
        raise RuntimeError("session is not an ExampleSession")


def check_graph_settings(graph_settings: any) -> None:
    """Check if graph_settings is a valid RFNoC graph settings object.

    It should have all members in GraphSettings._fields.
    Raises a RuntimeError if any member is missing.
    """
    if not graph_settings:
        raise RuntimeError("graph_settings is empty!")
    graph_settings_members = dir(graph_settings)
    missing_members = [
        member for member in GraphSettings._fields if member not in graph_settings_members
    ]
    if missing_members:
        raise RuntimeError(
            "graph_settings is missing member(s): " + ", ".join(missing_members)
        )


def _coerce_graph_settings(graph_settings: any):
    """Coerce channel selection or None into a GraphSettings object."""
    if graph_settings is None:
        return create_default_graph_settings((0, 1))

    if isinstance(graph_settings, GraphSettings):
        return graph_settings

    if isinstance(graph_settings, int) or isinstance(graph_settings, (list, tuple)):
        return create_default_graph_settings(graph_settings)

    check_graph_settings(graph_settings)
    return graph_settings


def _normalize_channels(channels):
    """Normalize channel selection to a validated list of unique channels."""
    if isinstance(channels, int):
        channel_list = [channels]
    elif isinstance(channels, (list, tuple)):
        channel_list = list(channels)
    else:
        raise RuntimeError("channels must be an int, list, or tuple")

    if len(channel_list) < 1:
        raise RuntimeError("At least one channel must be provided")
    if len(channel_list) > 2:
        raise RuntimeError("At most two channels are supported")
    if len(set(channel_list)) != len(channel_list):
        raise RuntimeError("Channels must be unique")

    for channel in channel_list:
        if channel not in (0, 1):
            raise RuntimeError(f"Invalid channel {channel}. Must be 0 or 1")

    return channel_list


def _normalize_value_list(values: any, name: str, expected_len: int, allow_scalar: bool = True):
    """Normalize scalar/list inputs into a list with expected_len entries."""
    if isinstance(values, (list, tuple)):
        value_list = list(values)
        if len(value_list) != expected_len:
            raise RuntimeError(f"{name} must have exactly {expected_len} element(s)")
        return value_list

    if allow_scalar:
        return [values for _ in range(expected_len)]

    raise RuntimeError(f"{name} must be a list or tuple with {expected_len} element(s)")


def _get_session_channels(session: ExampleSession):
    """Return deterministic channel ordering for helper APIs."""
    channels = sorted(session.radio_ctrls.keys())
    if len(channels) < 1:
        raise RuntimeError("No channels are configured in session.radio_ctrls")
    return channels


def _resolve_session_channels(session: ExampleSession, channels=None):
    """Resolve requested channels against the channels configured in session."""
    session_channels = _get_session_channels(session)
    if channels is None:
        return session_channels

    requested = _normalize_channels(channels)
    missing = [channel for channel in requested if channel not in session_channels]
    if missing:
        raise RuntimeError(
            f"Requested channel(s) {missing} are not configured in this session. "
            f"Available channels: {session_channels}"
        )
    return requested


def open_session(args: str, graph_settings: any = None) -> ExampleSession:
    """Open a session with the USRP device and setup the graph.

    Args:
        args: UHD device arguments string (e.g., "addr=192.168.10.2")
        graph_settings: GraphSettings named tuple, or channel selector
                   (0, 1, [0, 1], (0, 1)); defaults to both channels

    Returns:
        ExampleSession object with initialized graph and blocks
    """
    session = ExampleSession(args)
    if not session:
        raise RuntimeError("Failed to open Example session")
    else:
        print(f"ExampleSession opened, args: {args}")
        graph_settings = _coerce_graph_settings(graph_settings)
        session.setup_graph(graph_settings)
        print("RFNoC blocks connected - Graph setup done")
        return session


def find_aurora_block(graph, channel):
    """
    Find an Aurora block by trying multiple naming conventions.

    Args:
        graph: RFNoC graph
        channel: Channel number

    Returns:
        tuple: (block_id_str, block) where block_id_str is the string ID used

    Raises:
        RuntimeError: If block not found or NOC ID doesn't match Aurora
    """
    # Try Aurora# naming first (when OOT module is loaded)
    block_id_candidates = [
        f"0/Aurora#{channel}",
        f"0/Block#{channel}",
    ]

    for block_id in block_id_candidates:
        try:
            block = graph.get_block(block_id)
            # Verify it's actually an Aurora block by checking NOC ID
            noc_id = block.get_noc_id()
            if noc_id == AURORA_BLOCK_ID:
                return (block_id, block)
            else:
                print(
                    f"  WARNING: Block {block_id} has NOC ID "
                    f"0x{noc_id:08X}, expected 0x{AURORA_BLOCK_ID:08X}"
                )
        except (RuntimeError, LookupError):
            continue

    raise RuntimeError(f"Could not find Aurora block for channel {channel}")


def create_default_graph_settings(channels=(0, 1)):
    """Build GraphSettings for one or two selected channels."""
    channel_list = _normalize_channels(channels)

    return GraphSettings(
        tx_radios=channel_list,
        rx_radios=channel_list,
        tx_chans=[0 for _ in channel_list],
        rx_chans=[0 for _ in channel_list],
    )


def labview_open_session(
    device_args="",
    channels=(0, 1),
    rate=1.25e9,
    freq=1e9,
    rx_gain=0.0,
    tx_gain=0.0,
    spp=1024,
    fc_pause_count=100,
    fc_pause_threshold=160,
    fc_resume_threshold=200,
):
    """Open and configure session resources for LabVIEW integration."""
    channel_list = _normalize_channels(channels)
    graph_settings = create_default_graph_settings(channel_list)
    session = open_session(device_args, graph_settings)

    for channel in channel_list:
        aurora_ctrl = session.aurora_blocks[channel]
        radio_ctrl = session.radio_ctrls[channel]

        aurora_ctrl.set_fc_pause_count(fc_pause_count)
        aurora_ctrl.set_fc_pause_threshold(fc_pause_threshold)
        aurora_ctrl.set_fc_resume_threshold(fc_resume_threshold)
        aurora_ctrl.set_channel_stop_policy(channel_stop_policy.BUFFER)

        radio_ctrl.set_rate(rate)
        radio_ctrl.set_rx_frequency(freq, 0)
        radio_ctrl.set_tx_frequency(freq, 0)
        radio_ctrl.set_rx_gain(rx_gain, 0)
        radio_ctrl.set_tx_gain(tx_gain, 0)
        radio_ctrl.set_properties(uhd.types.DeviceAddr(f"spp={spp}"), 0)

    return session


def labview_wait_links(session: ExampleSession, channels=None, check_interval=0.1):
    """Block until all requested Aurora links are up."""
    check_session(session)
    for channel in _resolve_session_channels(session, channels):
        wait_for_link_up(session.aurora_blocks[channel], check_interval)


def labview_start(session: ExampleSession, channels=None, enable_tx=True, enable_rx=True):
    """Start selected TX/RX data paths."""
    check_session(session)
    for channel in _resolve_session_channels(session, channels):
        radio_ctrl = session.radio_ctrls[channel]

        if enable_tx:
            aurora_ctrl = session.aurora_blocks[channel]
            aurora_ctrl.set_channel_stop_policy(channel_stop_policy.BUFFER)
            aurora_ctrl.tx_datapath_enable(True)
            tx_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
            tx_cmd.stream_now = True
            try:
                radio_ctrl.issue_stream_cmd(tx_cmd, 0)
            except RuntimeError:
                pass

        if enable_rx:
            rx_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
            rx_cmd.stream_now = True
            radio_ctrl.issue_stream_cmd(rx_cmd, 0)


def labview_stop(session: ExampleSession, channels=None, enable_tx=True, enable_rx=True):
    """Stop selected TX/RX data paths."""
    check_session(session)
    for channel in _resolve_session_channels(session, channels):
        radio_ctrl = session.radio_ctrls[channel]

        if enable_tx:
            session.aurora_blocks[channel].tx_datapath_enable(False)
            tx_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont)
            try:
                radio_ctrl.issue_stream_cmd(tx_cmd, 0)
            except RuntimeError:
                pass

        if enable_rx:
            rx_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont)
            radio_ctrl.issue_stream_cmd(rx_cmd, 0)


def labview_close(session: ExampleSession, channels=None, enable_tx=True):
    """Final cleanup for LabVIEW shutdown."""
    check_session(session)
    for channel in _resolve_session_channels(session, channels):
        aurora_ctrl = session.aurora_blocks[channel]
        if enable_tx:
            aurora_ctrl.tx_datapath_enable(False)
        aurora_ctrl.set_channel_stop_policy(channel_stop_policy.DROP)

    close_session(session)


def wait_for_link_up(aurora_block, check_interval=0.1):
    """
    Wait for the Aurora link to come up.

    Args:
        aurora_block: AuroraBlockControl instance
        check_interval: How often to check link status in seconds
    """
    while not aurora_block.get_link_status():
        time.sleep(check_interval)


def connect_blocks(graph, radio_block, aurora_block, radio_port=0, aurora_port=0):
    """
    Connect Radio and Aurora blocks in the RFNoC graph.

    Args:
        graph: RFNoC graph instance
        radio_block: Radio block unique ID
        aurora_block: Aurora block unique ID
        radio_port: Radio port number
        aurora_port: Aurora port number
    """
    # Radio TX output -> Aurora RX input (Radio → Aurora, "RX" from radio perspective)
    graph.connect(radio_block, radio_port, aurora_block, aurora_port)

    # Aurora TX output -> Radio RX input (Aurora → Radio, "TX" from radio perspective)
    # Mark as back edge since this creates a cycle
    graph.connect(aurora_block, aurora_port, radio_block, radio_port, True)


def close_session(session: ExampleSession) -> None:
    """Close the session and release resources.
    
    Args:
        session: ExampleSession object to close
    """
    print("Closing Example session")
    del session


def configure_rx(
    session: ExampleSession,
    ch0_rx_freq: float,
    ch0_rx_gain: float,
    ch1_rx_freq: float,
    ch1_rx_gain: float,
):
    """Configure RX radios using explicit channel-0 and channel-1 inputs.

    Args:
        session: ExampleSession object
        ch0_rx_freq: RX frequency for channel 0 (Hz)
        ch0_rx_gain: RX gain for channel 0 (dB)
        ch1_rx_freq: RX frequency for channel 1 (Hz)
        ch1_rx_gain: RX gain for channel 1 (dB)

    Returns:
        List of actual RX frequencies in session channel order
    """
    check_session(session)
    channels = _get_session_channels(session)
    per_channel = {
        0: (ch0_rx_freq, ch0_rx_gain),
        1: (ch1_rx_freq, ch1_rx_gain),
    }

    actual_rx_freqs = []
    for channel in channels:
        rx_freq, rx_gain = per_channel[channel]
        radio_ctrl = session.radio_ctrls[channel]
        actual_rx_freq = radio_ctrl.set_rx_frequency(rx_freq, 0)
        radio_ctrl.set_rx_gain(rx_gain, 0)
        actual_rx_freqs.append(actual_rx_freq)
    return actual_rx_freqs


def configure_tx(
    session: ExampleSession,
    ch0_tx_freq: float,
    ch0_tx_gain: float,
    ch1_tx_freq: float,
    ch1_tx_gain: float,
):
    """Configure TX radios using explicit channel-0 and channel-1 inputs.

    Args:
        session: ExampleSession object
        ch0_tx_freq: TX frequency for channel 0 (Hz)
        ch0_tx_gain: TX gain for channel 0 (dB)
        ch1_tx_freq: TX frequency for channel 1 (Hz)
        ch1_tx_gain: TX gain for channel 1 (dB)

    Returns:
        List of actual TX frequencies in session channel order
    """
    check_session(session)
    channels = _get_session_channels(session)
    per_channel = {
        0: (ch0_tx_freq, ch0_tx_gain),
        1: (ch1_tx_freq, ch1_tx_gain),
    }

    actual_tx_freqs = []
    for channel in channels:
        tx_freq, tx_gain = per_channel[channel]
        radio_ctrl = session.radio_ctrls[channel]
        actual_tx_freq = radio_ctrl.set_tx_frequency(tx_freq, 0)
        radio_ctrl.set_tx_gain(tx_gain, 0)
        actual_tx_freqs.append(actual_tx_freq)
    return actual_tx_freqs


def configure_tx_aurora(session: ExampleSession, tx_aurora_settings_list: any) -> None:
    """Configure TX Aurora settings for all channels in this session."""
    check_session(session)
    channels = _get_session_channels(session)
    expected_len = len(channels)
    tx_aurora_settings_list = _normalize_value_list(
        tx_aurora_settings_list,
        "tx_aurora_settings_list",
        expected_len,
        allow_scalar=(expected_len == 1),
    )

    for idx, channel in enumerate(channels):
        tx_aurora_settings = tx_aurora_settings_list[idx]
        tx_aurora = session.aurora_blocks[channel]
        if tx_aurora_settings.policy:
            tx_aurora.set_channel_stop_policy(channel_stop_policy.DROP)
        else:
            tx_aurora.set_channel_stop_policy(channel_stop_policy.BUFFER)

        tx_aurora.set_fc_pause_count(tx_aurora_settings.pause_count)
        tx_aurora.set_fc_pause_threshold(tx_aurora_settings.pause_threshold)
        tx_aurora.set_fc_resume_threshold(tx_aurora_settings.resume_threshold)


def start_generation(session: ExampleSession) -> None:
    """Start TX datapath on both Aurora channels."""
    print("Starting generation...")
    check_session(session)
    channels = _get_session_channels(session)
    for channel in channels:
        session.aurora_blocks[channel].tx_datapath_enable(True)

def stop_generation(session: ExampleSession) -> None:
    """Stop TX datapath on both Aurora channels."""
    print("Stopping generation...")
    check_session(session)
    channels = _get_session_channels(session)
    for channel in channels:
        session.aurora_blocks[channel].tx_datapath_enable(False)


def start_acquisition(session: ExampleSession) -> None:
    """Start RX streaming on both channels."""
    print("Starting to receive...")
    check_session(session)
    channels = _get_session_channels(session)
    for channel in channels:
        stream_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.start_cont)
        stream_cmd.stream_now = True
        session.radio_ctrls[channel].issue_stream_cmd(stream_cmd, 0)


def stop_acquisition(session: ExampleSession) -> None:
    """Stop RX streaming on both channels."""
    print("Stop Rx streaming")
    check_session(session)
    channels = _get_session_channels(session)
    stream_cmd = uhd.types.StreamCMD(uhd.types.StreamMode.stop_cont)
    for channel in channels:
        session.radio_ctrls[channel].issue_stream_cmd(stream_cmd, 0)


def check_aurora_errors(session: ExampleSession):
    """Return list of per-link error records.

    Output format:
        [(crc_error_count, overflow_error_count), ...]

    The list follows session channel order (sorted by channel index).
    """
    check_session(session)
    result = []
    for channel in _get_session_channels(session):
        aurora = session.aurora_blocks[channel]
        crc_err = int(aurora.get_aurora_crc_error_counter())
        overflow = int(aurora.get_aurora_overflow_counter())

        result.append((int(crc_err), int(overflow)))

    return result


def check_aurora_status(session: ExampleSession):
    """Return list of per-link status records.

    Output format:
        [(link_status, rx_packet_count, tx_packet_count), ...]

    The list follows session channel order (sorted by channel index).
    Link values are booleans: True for UP, False for DOWN.
    """
    check_session(session)
    result = []
    for channel in _get_session_channels(session):
        aurora = session.aurora_blocks[channel]
        link = bool(aurora.get_link_status())
        rx_pkts = int(aurora.get_aurora_rx_packet_counter())
        tx_pkts = int(aurora.get_aurora_tx_packet_counter())

        result.append((link, int(rx_pkts), int(tx_pkts)))

    return result


