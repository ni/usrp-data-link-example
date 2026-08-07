# USRP Aurora FPGA Image

<p>
Download the FPGA bitfile from the appropriate directory and use the following command to flash it onto the USRP.
</p>
<ul>
<li>For <strong>X420</strong>, use the /x420 directory.</li>
<li>For <strong>X440</strong>, use the /x440 directory.</li>
</ul>
<p>
Replace the placeholders with the appropriate IP address and the path to the bitfile:
</p>
</p>
<pre><code>uhd_image_loader --args "type=x4xx,addr=&lt;IP address of device&gt;" --fpga-path &lt;path_to_bit&gt;</code></pre>
