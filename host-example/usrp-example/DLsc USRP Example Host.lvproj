<?xml version='1.0' encoding='UTF-8'?>
<Project Type="Project" LVVersion="23008000">
	<Property Name="NI.LV.All.SaveVersion" Type="Str">23.0</Property>
	<Property Name="NI.LV.All.SourceOnly" Type="Bool">true</Property>
	<Item Name="My Computer" Type="My Computer">
		<Property Name="NI.SortType" Type="Int">3</Property>
		<Property Name="server.app.propertiesEnabled" Type="Bool">true</Property>
		<Property Name="server.control.propertiesEnabled" Type="Bool">true</Property>
		<Property Name="server.tcp.enabled" Type="Bool">false</Property>
		<Property Name="server.tcp.port" Type="Int">0</Property>
		<Property Name="server.tcp.serviceName" Type="Str">My Computer/VI Server</Property>
		<Property Name="server.tcp.serviceName.default" Type="Str">My Computer/VI Server</Property>
		<Property Name="server.vi.callsEnabled" Type="Bool">true</Property>
		<Property Name="server.vi.propertiesEnabled" Type="Bool">true</Property>
		<Property Name="specify.custom.address" Type="Bool">false</Property>
		<Item Name="Python API" Type="Folder">
			<Item Name="Python Scripts" Type="Folder">
				<Item Name="aurora_block_control_python.py" Type="Document" URL="../Python_Script/aurora_block_control_python.py"/>
				<Item Name="x4xx_aurora_streaming.py" Type="Document" URL="../Python_Script/x4xx_aurora_streaming.py"/>
			</Item>
			<Item Name="Python VI" Type="Folder">
				<Item Name="Open Session.vi" Type="VI" URL="../Python_API/Open Session.vi"/>
				<Item Name="Configure Tx Parameters.vi" Type="VI" URL="../Python_API/Configure Tx Parameters.vi"/>
				<Item Name="Stop Acquisition.vi" Type="VI" URL="../Python_API/Stop Acquisition.vi"/>
				<Item Name="Start Acquisition.vi" Type="VI" URL="../Python_API/Start Acquisition.vi"/>
				<Item Name="Stop Generation.vi" Type="VI" URL="../Python_API/Stop Generation.vi"/>
				<Item Name="Check Aurora Status.vi" Type="VI" URL="../Python_API/Check Aurora Status.vi"/>
				<Item Name="Start Generation.vi" Type="VI" URL="../Python_API/Start Generation.vi"/>
				<Item Name="Close Session.vi" Type="VI" URL="../Python_API/Close Session.vi"/>
				<Item Name="Configure Tx.vi" Type="VI" URL="../Python_API/Configure Tx.vi"/>
			</Item>
		</Item>
		<Item Name="x4xx usrp aurora streaming.vi" Type="VI" URL="../x4xx usrp aurora streaming.vi"/>
		<Item Name="Dependencies" Type="Dependencies"/>
		<Item Name="Build Specifications" Type="Build"/>
	</Item>
</Project>
