# USRP Aurora Control Example

<p>
This example demonstrates X4xx USRP control for Aurora streaming for multichannel operation.
</p>
<blockquote>
<strong>Important:</strong> This example must be executed together with a compatible Aurora endpoint application running on an NI high-speed serial device. To establish the Aurora link and enable data transfer, the corresponding example must be running simultaneously on either a <strong>PXIe-7903 FPGA Coprocessor</strong> or a <strong>PXIe-6594 High-Speed Serial Instrument</strong>. For additional information, refer to the NI Data Link Test Framework documentation.
</blockquote>
<ol>
<li>
Download and open <strong>DLsc USRP Example Host.lvproj</strong>, which contains all required project files and VIs. The main application VI is <strong>x4xx usrp aurora streaming.vi</strong>.
<p align="center">
figures/x4xx-usrp-example-host-project.PNG
</p>
</li>
<li>
Launch the VI and review the front panel configuration options described below.
<ul>
<li>
<strong>USRP arguments</strong> control is used to configure the USRP IP address and master clock rate of the USRP. For the <strong>USRP X420</strong>, the supported master clock rates are <strong>250 MS/s</strong> and <strong>1250 MS/s</strong>. For the <strong>USRP X440</strong>, refer to the appropriate documentation for supported master clock rate values.
</li>
<li>
<strong>Channels</strong> control specifies which RF channel(s) are enabled for both transmit (Tx) and receive (Rx) operation. The following channel configurations are supported:

<ul>
<li><strong>0</strong> – Enables Channel 0 only, corresponding to TX/RX0 and RX1 antenna ports of Daughterboard 0 (DB0).</li>
<li><strong>1</strong> – Enables Channel 1 only, corresponding to TX/RX0 and RX1 antenna ports of Daughterboard 1 (DB1).</li>
<li><strong>0,1</strong> – Enables both Channel 0 (DB0) and Channel 1 (DB1) simultaneously for multi-channel operation.</li>
</ul>
</li>
</ul>
</li>
</ol>
