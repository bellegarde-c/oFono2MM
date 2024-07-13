from dbus_next.service import (ServiceInterface,
                               method, dbus_property, signal)
from dbus_next.constants import PropertyAccess
from dbus_next import Variant, DBusError, BusType

from ofono2mm.mm_modem_3gpp import MMModem3gppInterface
from ofono2mm.mm_modem_3gpp_ussd import MMModem3gppUssdInterface
from ofono2mm.mm_modem_3gpp_profile_manager import MMModem3gppProfileManagerInterface
from ofono2mm.mm_modem_messaging import MMModemMessagingInterface
from ofono2mm.mm_modem_simple import MMModemSimpleInterface
from ofono2mm.mm_modem_firmware import MMModemFirmwareInterface
from ofono2mm.mm_modem_cdma import MMModemCDMAInterface
from ofono2mm.mm_modem_time import MMModemTimeInterface
from ofono2mm.mm_modem_sar import MMModemSarInterface
from ofono2mm.mm_modem_oma import MMModemOmaInterface
from ofono2mm.mm_modem_signal import MMModemSignalInterface
from ofono2mm.mm_modem_location import MMModemLocationInterface
from ofono2mm.mm_sim import MMSimInterface
from ofono2mm.mm_bearer import MMBearerInterface
from ofono2mm.mm_modem_voice import MMModemVoiceInterface

import asyncio

bearer_i = 0

class MMModemInterface(ServiceInterface):
    def __init__(self, loop, index, bus, ofono_client, modem_name):
        super().__init__('org.freedesktop.ModemManager1.Modem')
        self.loop = loop
        self.index = index
        self.bus = bus
        self.ofono_client = ofono_client
        self.ofono_proxy = self.ofono_client["ofono_modem"][modem_name]
        self.modem_name = modem_name
        self.ofono_modem = self.ofono_proxy['org.ofono.Modem']
        self.ofono_props = {}
        self.ofono_interfaces = {}
        self.ofono_interface_props = {}
        self.mm_cell_type = 0 # on runtime unknown MM_CELL_TYPE_UNKNOWN
        self.mm_modem3gpp_interface = False
        self.mm_modem_messaging_interface = False
        self.mm_sim_interface = False
        self.sim = Variant('o', f'/org/freedesktop/ModemManager1/SIM/{self.index}')
        self.bearers = {}
        self.props = {
            'Sim': Variant('o', '/'),
            'SimSlots': Variant('ao', [f'/org/freedesktop/ModemManager1/SIM/{self.index}']),
            'PrimarySimSlot': Variant('u', 0),
            'Bearers': Variant('ao', []),
            'SupportedCapabilities': Variant('au', [0]), # on runtime none MM_MODEM_CAPABILITY_NONE
            'CurrentCapabilities': Variant('u', 0), # on runtime none MM_MODEM_CAPABILITY_NONE
            'MaxBearers': Variant('u', 4),
            'MaxActiveBearers': Variant('u', 2),
            'MaxActiveMultiplexedBearers': Variant('u', 2),
            'Manufacturer': Variant('s', 'ofono'),
            'Model': Variant('s', ''),
            'Revision': Variant('s', '10000'),
            'CarrierConfiguration': Variant('s', ''),
            'CarrierConfigurationRevision': Variant('s', '0'),
            'HardwareRevision': Variant('s', '1000'),
            'DeviceIdentifier': Variant('s', self.modem_name),
            'Device': Variant('s', self.modem_name),
            'Physdev': Variant('s', '/dev/binder'),
            'Drivers': Variant('as', ['binder']),
            'Plugin': Variant('s', 'ofono2mm'),
            'PrimaryPort': Variant('s', self.modem_name),
            'Ports': Variant('a(su)', [[self.modem_name, 0]]), # on runtime unknown MM_MODEM_PORT_TYPE_UNKNOWN
            'EquipmentIdentifier': Variant('s', ''),
            'UnlockRequired': Variant('u', 0), # on runtime unknown MM_MODEM_LOCK_UNKNOWN
            'UnlockRetries': Variant('a{uu}', {}),
            'State': Variant('i', 6), # on runtime enabled MM_MODEM_STATE_ENABLED
            'StateFailedReason': Variant('u', 0), # on runtime unknown MM_MODEM_STATE_CHANGE_REASON_UNKNOWN
            'AccessTechnologies': Variant('u', 0), # on runtime unknown MM_MODEM_ACCESS_TECHNOLOGY_UNKNOWN
            'SignalQuality': Variant('(ub)', [0, False]),
            'OwnNumbers': Variant('as', []),
            'PowerState': Variant('u', 3), # on runtime power on MM_MODEM_POWER_STATE_ON
            'SupportedModes': Variant('a(uu)', [[0, 0]]), # on runtime allowed mode none, preferred mode none MM_MODEM_MODE_NONE
            'CurrentModes': Variant('(uu)', [0, 0]), # on runtime allowed mode none, preferred mode none MM_MODEM_MODE_NONE
            'SupportedBands': Variant('au', []),
            'CurrentBands': Variant('au', []),
            'SupportedIpFamilies': Variant('u', 3) # hardcoded value ipv4 and ipv6 MM_BEARER_IP_FAMILY_IPV4V6
        }

    async def init_ofono_interfaces(self):
        for iface in self.ofono_props['Interfaces'].value:
            await self.add_ofono_interface(iface)

        await self.check_ofono_contexts()

    async def add_ofono_interface(self, iface):
        self.ofono_interfaces.update({
            iface: self.ofono_proxy[iface]
        })

        try:
            self.ofono_interface_props.update({
                iface: await self.ofono_interfaces[iface].call_get_properties()
            })

            if self.mm_modem3gpp_interface:
                self.mm_modem3gpp_interface.ofono_interface_props = self.ofono_interface_props.copy()
            if self.mm_sim_interface:
                self.mm_sim_interface.ofono_interface_props = self.ofono_interface_props.copy()

            self.ofono_interfaces[iface].on_property_changed(self.ofono_interface_changed(iface))
        except DBusError:
            self.ofono_interface_props.update({
                iface: {}
            })

            if self.mm_modem3gpp_interface:
                self.mm_modem3gpp_interface.ofono_interface_props = self.ofono_interface_props.copy()
            if self.mm_sim_interface:
                self.mm_sim_interface.ofono_interface_props = self.ofono_interface_props.copy()

            self.ofono_interfaces[iface].on_property_changed(self.ofono_interface_changed(iface))
        except AttributeError:
            pass

        if self.mm_modem3gpp_interface:
            self.mm_modem3gpp_interface.set_props()
        if self.mm_sim_interface:
            self.mm_sim_interface.set_props()
        if self.mm_modem_messaging_interface and iface == "org.ofono.MessageManager":
            self.mm_modem_messaging_interface.set_props()
            await self.mm_modem_messaging_interface.init_messages()
        if iface == "org.ofono.ConnectionManager":
            await self.check_ofono_contexts()

    async def remove_ofono_interface(self, iface):
        if iface in self.ofono_interfaces:
            self.ofono_interfaces.pop(iface)
        if iface in self.ofono_interface_props:
            self.ofono_interface_props.pop(iface)

        self.set_props()

        if self.mm_modem3gpp_interface:
            self.mm_modem3gpp_interface.ofono_interface_props = self.ofono_interface_props.copy()
            self.mm_modem3gpp_interface.set_props()
        if self.mm_sim_interface:
            self.mm_sim_interface.ofono_interface_props = self.ofono_interface_props.copy()
            self.mm_sim_interface.set_props()

    async def init_mm_sim_interface(self):
        self.mm_sim_interface = MMSimInterface(self.index, self.bus, self.ofono_client, self.modem_name, self.ofono_modem, self.ofono_props, self.ofono_interfaces, self.ofono_interface_props)
        self.bus.export(f'/org/freedesktop/ModemManager1/SIM/{self.index}', self.mm_sim_interface)
        self.mm_sim_interface.set_props()

    async def init_mm_3gpp_interface(self):
        self.mm_modem3gpp_interface = MMModem3gppInterface(self.index, self.bus, self.ofono_client, self.modem_name, self.ofono_modem, self.ofono_props, self.ofono_interfaces, self.ofono_interface_props)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem3gpp_interface)
        self.mm_modem3gpp_interface.set_props()

    async def init_mm_3gpp_ussd_interface(self):
        self.mm_modem3gpp_ussd_interface = MMModem3gppUssdInterface(self.index, self.bus, self.ofono_client, self.modem_name, self.ofono_modem, self.ofono_props, self.ofono_interfaces, self.ofono_interface_props)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem3gpp_ussd_interface)

    async def init_mm_3gpp_profile_manager_interface(self):
        self.mm_modem3gpp_profile_manager_interface = MMModem3gppProfileManagerInterface(self.index, self.bus, self.ofono_client, self.modem_name, self.ofono_modem, self.ofono_props, self.ofono_interfaces, self.ofono_interface_props)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem3gpp_profile_manager_interface)

    async def init_mm_simple_interface(self):
        self.mm_modem_simple_interface = MMModemSimpleInterface(self, self.ofono_interfaces, self.ofono_interface_props)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem_simple_interface)
        await self.mm_modem_simple_interface.set_props()

    async def init_mm_firmware_interface(self):
        self.mm_modem_firmware_interface = MMModemFirmwareInterface(self)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem_firmware_interface)
        self.mm_modem_firmware_interface.set_props()

    async def init_mm_time_interface(self):
        self.mm_modem_time_interface = MMModemTimeInterface(self.index, self.bus, self.ofono_client, self.modem_name, self.ofono_modem, self.ofono_props, self.ofono_interfaces, self.ofono_interface_props)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem_time_interface)

        if 'org.ofono.NetworkTime' in self.ofono_interfaces:
            await self.mm_modem_time_interface.init_time()

    async def init_mm_cdma_interface(self):
        self.mm_modem_cdma_interface = MMModemCDMAInterface(self)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem_cdma_interface)

    async def init_mm_sar_interface(self):
        self.mm_modem_sar_interface = MMModemSarInterface(self)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem_sar_interface)

    async def init_mm_oma_interface(self):
        self.mm_modem_oma_interface = MMModemOmaInterface(self)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem_oma_interface)

    async def init_mm_signal_interface(self):
        self.mm_modem_signal_interface = MMModemSignalInterface(self, self.ofono_interfaces, self.ofono_interface_props)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem_signal_interface)
        self.mm_modem_signal_interface.set_props()

    async def init_mm_location_interface(self):
        self.mm_modem_location_interface = MMModemLocationInterface(self)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem_location_interface)

    async def init_mm_voice_interface(self):
        self.mm_modem_voice_interface = MMModemVoiceInterface(self.index, self.bus, self.ofono_client, self.modem_name, self.ofono_modem, self.ofono_props, self.ofono_interfaces, self.ofono_interface_props)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem_voice_interface)

        if 'org.ofono.VoiceCallManager' in self.ofono_interfaces:
            self.mm_modem_voice_interface.set_props()
            await self.mm_modem_voice_interface.init_calls()

    async def init_mm_messaging_interface(self):
        self.mm_modem_messaging_interface = MMModemMessagingInterface(self.index, self.bus, self.ofono_client, self.modem_name, self.ofono_modem, self.ofono_props, self.ofono_interfaces, self.ofono_interface_props)
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.index}', self.mm_modem_messaging_interface)

        if 'org.ofono.MessageManager' in self.ofono_interfaces:
            self.mm_modem_messaging_interface.set_props()
            await self.mm_modem_messaging_interface.init_messages()

    async def check_ofono_contexts(self):
        global bearer_i
        if not 'org.ofono.ConnectionManager' in self.ofono_interfaces:
            return

        contexts = await self.ofono_interfaces['org.ofono.ConnectionManager'].call_get_contexts();
        old_bearer_list = self.props['Bearers'].value
        for ctx in contexts:
            if ctx[1]['Type'].value == "internet":
                mm_bearer_interface = MMBearerInterface(self.index, self.bus, self.ofono_client, self.modem_name, self.ofono_modem, self.ofono_props, self.ofono_interfaces, self.ofono_interface_props, self)

                ip_method = 0
                if 'Method' in ctx[1]['Settings'].value:
                    if ctx[1]['Settings'].value['Method'].value == "static":
                        ip_method = 2
                    if ctx[1]['Settings'].value['Method'].value == "dhcp":
                        ip_method = 3

                ip_address = ''
                if 'Address' in ctx[1]['Settings'].value:
                    ip_address = ctx[1]['Settings'].value['Address'].value

                ip_dns = []
                if 'DomainNameServers' in ctx[1]['Settings'].value:
                    ip_dns = ctx[1]['Settings'].value['DomainNameServers'].value

                ip_gateway = ''
                if 'Gateway' in ctx[1]['Settings'].value:
                    ip_gateway = ctx[1]['Settings'].value['Gateway'].value

                mm_bearer_interface.props.update({
                    "Interface": ctx[1]['Settings'].value.get("Interface", Variant('s', '')),
                    "Connected": ctx[1]['Active'],
                    "Ip4Config": Variant('a{sv}', {
                        "method": Variant('u', ip_method),
                        "dns1": Variant('s', ip_dns[0] if len(ip_dns) > 0 else ''),
                        "dns2": Variant('s', ip_dns[1] if len(ip_dns) > 1 else ''),
                        "dns3": Variant('s', ip_dns[2] if len(ip_dns) > 2 else ''),
                        "gateway": Variant('s', ip_gateway)
                    }),
                    "Properties": Variant('a{sv}', {
                        "apn": ctx[1]['AccessPointName']
                    })
                })

                if 'Interface' in ctx[1]['Settings'].value:
                    self.props['Ports'].value.append([ctx[1]['Settings'].value['Interface'].value, 2]) # port type AT MM_MODEM_PORT_TYPE_AT
                    self.emit_properties_changed({'Ports': self.props['Ports'].value})

                ofono_ctx_interface = self.ofono_client["ofono_context"][ctx[0]]["org.ofono.ConnectionContext"]
                ofono_ctx_interface.on_property_changed(mm_bearer_interface.ofono_context_changed)
                mm_bearer_interface.ofono_ctx = ctx[0]
                self.bus.export(f'/org/freedesktop/ModemManager/Bearer/{bearer_i}', mm_bearer_interface)
                self.props['Bearers'].value.append(f'/org/freedesktop/ModemManager/Bearer/{bearer_i}')
                self.bearers[f'/org/freedesktop/ModemManager/Bearer/{bearer_i}'] = mm_bearer_interface
                bearer_i += 1

        if self.props['Bearers'].value == old_bearer_list:
            self.emit_properties_changed({'Bearers': self.props['Bearers'].value})

        self.ofono_interfaces['org.ofono.ConnectionManager'].on_context_added(self.ofono_context_added)

    def ofono_context_added(self, path, properties):
        global bearer_i
        if properties['Type'] == "internet":
            mm_bearer_interface = MMBearerInterface(self.index, self.bus, self.ofono_client, self.modem_name, self.ofono_modem, self.ofono_props, self.ofono_interfaces, self.ofono_interface_props, self)

            ip_method = 0
            if 'Method' in properties['Settings'].value:
                if properties['Settings'].value['Method'].value == "static":
                    ip_method = 2
                elif properties['Settings'].value['Method'].value == "dhcp":
                    ip_method = 3

            ip_address = ''
            if 'Address' in properties['Settings'].value:
                ip_address = properties['Settings'].value['Address'].value

            ip_dns = []
            if 'DomainNameServers' in properties['Settings'].value:
                ip_dns = properties['Settings'].value['DomainNameServers'].value

            ip_gateway = ''
            if 'Gateway' in properties['Settings'].value:
                ip_gateway = properties['Settings'].value['Gateway'].value

            mm_bearer_interface.props.update({
                "Interface": properties['Settings'].value['Interface'] if 'Interface' in properties['Settings'].value else Variant('s', ''),
                "Connected": properties['Active'],
                "Ip4Config": Variant('a{sv}', {
                    "method": Variant('u', ip_method),
                    "dns1": Variant('s', ip_dns[0] if len(ip_dns) > 0 else ''),
                    "dns2": Variant('s', ip_dns[1] if len(ip_dns) > 1 else ''),
                    "dns3": Variant('s', ip_dns[2] if len(ip_dns) > 2 else ''),
                    "gateway": Variant('s', ip_gateway)
                }),
                "Properties": Variant('a{sv}', {
                    "apn": properties['AccessPointName']
                })
            })

            if 'Interface' in properties['Settings'].value:
                self.props['Ports'].value.append([properties['Settings'].value['Interface'].value, 2])
                self.emit_properties_changed({'Ports': self.props['Ports'].value})

            ofono_ctx_interface = self.ofono_client["ofono_context"][path]['org.ofono.ConnectionContext']
            ofono_ctx_interface.on_property_changed(mm_bearer_interface.ofono_context_changed)
            mm_bearer_interface.ofono_ctx = path
            self.bus.export(f'/org/freedesktop/ModemManager/Bearer/{bearer_i}', mm_bearer_interface)
            self.props['Bearers'].value.append(f'/org/freedesktop/ModemManager/Bearer/{bearer_i}')
            self.bearers[f'/org/freedesktop/ModemManager/Bearer/{bearer_i}'] = mm_bearer_interface
            bearer_i += 1
            self.emit_properties_changed({'Bearers': self.props['Bearers'].value})

    def set_props(self):
        old_props = self.props.copy()
        old_state = self.props['State'].value
        self.props['UnlockRequired'] = Variant('u', 1) # modem is unlocked MM_MODEM_LOCK_NONE
        if self.ofono_props['Powered'].value and 'org.ofono.SimManager' in self.ofono_interface_props:
            if 'Present' in self.ofono_interface_props['org.ofono.SimManager']:
                if self.ofono_interface_props['org.ofono.SimManager']['Present'].value and 'PinRequired' in self.ofono_interface_props['org.ofono.SimManager']:
                    if self.ofono_interface_props['org.ofono.SimManager']['PinRequired'].value == 'none':
                        self.props['UnlockRequired'] = Variant('u', 1) # modem is unlocked MM_MODEM_LOCK_NONE
                        if self.ofono_props['Online'].value:
                            if 'org.ofono.NetworkRegistration' in self.ofono_interface_props:
                                if ("Status" in self.ofono_interface_props['org.ofono.NetworkRegistration']):
                                    if self.ofono_interface_props['org.ofono.NetworkRegistration']['Status'].value == 'registered' or self.ofono_interface_props['org.ofono.NetworkRegistration']['Status'].value == 'roaming':
                                        self.props['State'] = Variant('i', 8) # modem is registered MM_MODEM_STATE_REGISTERED
                                        if 'Strength' in self.ofono_interface_props['org.ofono.NetworkRegistration']:
                                            self.props['SignalQuality'] = Variant('(ub)', [self.ofono_interface_props['org.ofono.NetworkRegistration']['Strength'].value, True])
                                    elif self.ofono_interface_props['org.ofono.NetworkRegistration']['Status'].value == 'searching':
                                        self.props['State'] = Variant('i', 7) # modem is searching MM_MODEM_STATE_SEARCHING
                                    else:
                                        self.props['State'] = Variant('i', 6) # modem is enabled MM_MODEM_STATE_ENABLED
                                else:
                                    self.props['State'] = Variant('i', 6) # modem is enabled MM_MODEM_STATE_ENABLED
                            else:
                                self.props['State'] = Variant('i', 6) # modem is enabled MM_MODEM_STATE_ENABLED
                        else:
                            self.props['State'] = Variant('i', 3) # modem is disabled MM_MODEM_STATE_DISABLED

                        self.props['UnlockRequired'] = Variant('u', 1) # modem is unlocked MM_MODEM_LOCK_NONE
                    else:
                        self.props['UnlockRequired'] = Variant('u', 2) # modem needs a pin MM_MODEM_LOCK_SIM_PIN
                        self.props['State'] = Variant('i', 2)

                    self.props['Sim'] = self.sim
                    self.props['StateFailedReason'] = Variant('i', 0) # no failure MM_MODEM_STATE_FAILED_REASON_NONE
                else:
                    self.props['Sim'] = Variant('o', '/')
                    self.props['State'] = Variant('i', -1) # state unknown
                    self.props['StateFailedReason'] = Variant('i', 2) # sim missing MM_MODEM_STATE_FAILED_REASON_SIM_MISSING
            else:
                self.props['State'] = Variant('i', -1) # state unknown
                self.props['StateFailedReason'] = Variant('i', 2) # sim missing MM_MODEM_STATE_FAILED_REASON_SIM_MISSING

            self.props['PowerState'] = Variant('i', 3) # power is on MM_MODEM_POWER_STATE_ON
        else:
            self.props['State'] = Variant('i', 3) # modem is disabled MM_MODEM_STATE_DISABLED
            self.props['PowerState'] = Variant('i', 1) # power is off MM_MODEM_POWER_STATE_OFF

        if 'org.ofono.SimManager' in self.ofono_interface_props:
            self.props['OwnNumbers'] = Variant('as', self.ofono_interface_props['org.ofono.SimManager']['SubscriberNumbers'].value if 'SubscriberNumbers' in self.ofono_interface_props['org.ofono.SimManager'] else [])

            if 'Retries' in self.ofono_interface_props['org.ofono.SimManager']:
                if 'pin' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    pin = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['pin']
                else:
                    pin = -1

                if 'pin2' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    pin2 = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['pin2']
                else:
                    pin2 = -1

                if 'puk' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    puk = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['puk']
                else:
                    puk = -1

                if 'puk2' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    puk2 = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['puk2']
                else:
                    puk2 = -1

                if 'service' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    service = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['service']
                else:
                    service = -1

                if 'servicepuk' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    servicepuk = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['servicepuk']
                else:
                    servicepuk = -1

                if 'network' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    network = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['network']
                else:
                    network = -1

                if 'networkpuk' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    networkpuk = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['networkpuk']
                else:
                    networkpuk = -1

                if 'corp' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    corp = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['corp']
                else:
                    corp = -1

                if 'corppuk' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    corppuk = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['corppuk']
                else:
                    corppuk = -1

                if 'netsub' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    netsub = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['netsub']
                else:
                    netsub = -1

                if 'netsubpuk' in self.ofono_interface_props['org.ofono.SimManager']['Retries'].value:
                    netsubpuk = self.ofono_interface_props['org.ofono.SimManager']['Retries'].value['netsubpuk']
                else:
                    netsubpuk = -1

                unlock_retries = {}

                if pin != -1:
                    unlock_retries[2] = pin # MM_MODEM_LOCK_SIM_PIN
                if pin2 != -1:
                    unlock_retries[3] = pin2 # MM_MODEM_LOCK_SIM_PIN2
                if puk != -1:
                    unlock_retries[4] = puk # MM_MODEM_LOCK_SIM_PUK
                if puk2 != -1:
                    unlock_retries[5] = puk2 # MM_MODEM_LOCK_SIM_PUK2
                if service != -1:
                    unlock_retries[6] = service # MM_MODEM_LOCK_PH_SP_PIN
                if servicepuk != -1:
                    unlock_retries[7] = servicepuk # MM_MODEM_LOCK_PH_SP_PUK
                if network != -1:
                    unlock_retries[8] = network # MM_MODEM_LOCK_PH_NET_PIN
                if networkpuk != -1:
                    unlock_retries[9] = networkpuk # MM_MODEM_LOCK_PH_NET_PUK
                if corp != -1:
                    unlock_retries[11] = corp # MM_MODEM_LOCK_PH_CORP_PIN
                if corppuk != -1:
                    unlock_retries[12] = corppuk # MM_MODEM_LOCK_PH_CORP_PUK
                if netsub != -1:
                    unlock_retries[15] = netsub # MM_MODEM_LOCK_PH_NETSUB_PIN
                if netsubpuk != -1:
                    unlock_retries[16] = netsubpuk # MM_MODEM_LOCK_PH_NETSUB_PUK
            else:
                unlock_retries = {}

            self.props['UnlockRetries'] = Variant('a{uu}', unlock_retries)
        else:
            self.props['OwnNumbers'] = Variant('as', [])
            self.props['UnlockRetries'] = Variant('a{uu}', {})

        if 'org.ofono.NetworkRegistration' in self.ofono_interface_props and self.props['State'].value == 8:
            if "Technology" in self.ofono_interface_props['org.ofono.NetworkRegistration']:
                current_tech = 0
                if self.ofono_interface_props['org.ofono.NetworkRegistration']["Technology"].value == "nr":
                    current_tech |= 1 << 15 # network is 5g MM_MODEM_ACCESS_TECHNOLOGY_5GNR
                    self.mm_cell_type = 6 # cell type is 5g MM_CELL_TYPE_5GNR
                elif self.ofono_interface_props['org.ofono.NetworkRegistration']["Technology"].value == "lte":
                    current_tech |= 1 << 14 # network is lte MM_MODEM_ACCESS_TECHNOLOGY_LTE
                    self.mm_cell_type = 5 # cell type is lte MM_CELL_TYPE_LTE
                elif self.ofono_interface_props['org.ofono.NetworkRegistration']["Technology"].value == "hspa":
                    current_tech |= 1 << 8 # network is hspa MM_MODEM_ACCESS_TECHNOLOGY_HSPA
                    self.mm_cell_type = 3 # cell type is umts MM_CELL_TYPE_UMTS
                elif self.ofono_interface_props['org.ofono.NetworkRegistration']["Technology"].value == "hsupa":
                    current_tech |= 1 << 7 # network is hsupa MM_MODEM_ACCESS_TECHNOLOGY_HSUPA
                    self.mm_cell_type = 3 # cell type is umts MM_CELL_TYPE_UMTS
                elif self.ofono_interface_props['org.ofono.NetworkRegistration']["Technology"].value == "hsdpa":
                    current_tech |= 1 << 6 # network is hsdpa MM_MODEM_ACCESS_TECHNOLOGY_HSDPA
                    self.mm_cell_type = 3 # cell type is umts MM_CELL_TYPE_UMTS
                elif self.ofono_interface_props['org.ofono.NetworkRegistration']["Technology"].value == "umts":
                    current_tech |= 1 << 5 # network is umts MM_MODEM_ACCESS_TECHNOLOGY_UMTS
                    self.mm_cell_type = 3 # cell type is umts MM_CELL_TYPE_UMTS
                elif self.ofono_interface_props['org.ofono.NetworkRegistration']["Technology"].value == "edge":
                    current_tech |= 1 << 4 # network is gsm MM_MODEM_ACCESS_TECHNOLOGY_GSM
                    self.mm_cell_type = 2 # cell type is gsm MM_CELL_TYPE_GSM
                elif self.ofono_interface_props['org.ofono.NetworkRegistration']["Technology"].value == "gprs":
                    current_tech |= 1 << 3 # network is gsm MM_MODEM_ACCESS_TECHNOLOGY_GSM
                    self.mm_cell_type = 2 # cell type is gsm MM_CELL_TYPE_GSM
                elif self.ofono_interface_props['org.ofono.NetworkRegistration']["Technology"].value == "gsm":
                    current_tech |= 1 << 1 # network is gsm MM_MODEM_ACCESS_TECHNOLOGY_GSM
                    self.mm_cell_type = 2 # cell type is gsm MM_CELL_TYPE_GSM

                self.props['AccessTechnologies'] = Variant('u', current_tech)
            else:
                self.props['AccessTechnologies'] = Variant('u', 0) # network is unknown MM_MODEM_ACCESS_TECHNOLOGY_UNKNOWN
        else:
            self.props['AccessTechnologies'] = Variant('u', 0)
            self.props['SignalQuality'] = Variant('(ub)', [0, False])

        caps = 0
        modes = 0
        pref = 0
        supported_bands = []
        gsm_bands = [1, 2, 3, 4, 14, 15, 16, 17, 18, 19, 20]
        umts_bands = [5, 6, 7, 8, 9, 10, 11, 12, 13, 210, 211, 212, 213, 214, 219, 220, 221, 222, 225, 226, 232]
        lte_bands = [31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 115]
        nr_bands = [301, 302, 303, 305, 307, 308, 312, 313, 314, 318, 320, 325, 326, 328, 329, 330, 334, 338, 339, 340, 341, 348, 350, 351, 353, 365, 366, 370, 371, 374, 375, 376, 377, 378, 379, 380, 381, 382, 383, 384, 386, 389, 390, 391, 392, 393, 394, 395, 557, 558, 560, 561]
        if 'org.ofono.RadioSettings' in self.ofono_interface_props:
            if 'AvailableTechnologies' in self.ofono_interface_props['org.ofono.RadioSettings']:
                ofono_techs = self.ofono_interface_props['org.ofono.RadioSettings']['AvailableTechnologies'].value
                if 'gsm' in ofono_techs:
                    caps |= 4
                    modes |= 2
                    supported_bands.extend(gsm_bands)
                if 'umts' in ofono_techs:
                    caps |= 4
                    modes |= 4
                    supported_bands.extend(umts_bands)
                if 'lte' in ofono_techs:
                    caps |= 8
                    modes |= 8
                    supported_bands.extend(lte_bands)
                if 'nr' in ofono_techs:
                    caps |= 16
                    modes |= 16
                    supported_bands.extend(nr_bands)

            if 'TechnologyPreference' in self.ofono_interface_props['org.ofono.RadioSettings']:
                ofono_pref =  self.ofono_interface_props['org.ofono.RadioSettings']['TechnologyPreference'].value
                if ofono_pref == 'nr':
                    pref = 16 # current mode nr MM_MODEM_MODE_5G
                if ofono_pref == 'lte':
                    pref = 8 # current mode lte MM_MODEM_MODE_4G
                if ofono_pref == 'umts':
                    pref = 4 # current mode umts MM_MODEM_MODE_3G
                if ofono_pref == 'gsm':
                    pref = 2 # current mode gsm MM_MODEM_MODE_2G

        self.props['CurrentCapabilities'] = Variant('u', caps)
        self.props['SupportedCapabilities'] = Variant('au', [caps])

        self.props['CurrentBands'] = Variant('au', supported_bands)
        self.props['SupportedBands'] = Variant('au', supported_bands)

        if caps == 0:
            self.props['CurrentCapabilities'] = Variant('u', 4) # lte MM_MODEM_CAPABILITY_LTE
            self.props['SupportedCapabilities'] = Variant('au', [4]) # lte MM_MODEM_CAPABILITY_LTE

        supported_modes = []
        if modes == 30:
            supported_modes.append([30, 16])
            supported_modes.append([14, 8])
            supported_modes.append([6, 4])
            supported_modes.append([2, 0])
        if modes == 28:
            supported_modes.append([28, 0])
        if modes == 26:
            supported_modes.append([26, 0])
        if modes == 24:
            supported_modes.append([24, 0])
        if modes == 22:
            supported_modes.append([22, 0])
        if modes == 20:
            supported_modes.append([20, 0])
        if modes == 18:
            supported_modes.append([18, 0])
        if modes == 16:
            supported_modes.append([16, 0])
        if modes == 14:
            supported_modes.append([14, 8])
            supported_modes.append([6, 4])
            supported_modes.append([2, 0])
        if modes == 12:
            supported_modes.append([12, 8])
            supported_modes.append([4, 0])
        if modes == 10:
            supported_modes.append([10, 8])
            supported_modes.append([2, 0])
        if modes == 8:
            supported_modes.append([8, 0])
        if modes == 6:
            supported_modes.append([6, 4])
            supported_modes.append([2, 0])
        if modes == 4:
            supported_modes.append([4, 0])
        if modes == 2:
            supported_modes.append([2, 0])

        self.props['SupportedModes'] = Variant('a(uu)', supported_modes)
        for mode in supported_modes:
            if mode[1] == pref:
                self.props['CurrentModes'] = Variant('(uu)', [mode[0], pref])
            if mode[1] == 0 and mode[0] == pref:
                self.props['CurrentModes'] = Variant('(uu)', [mode[0], 0]) # current mode none MM_MODEM_MODE_NONE

        if supported_modes == []:
            self.props['SupportedModes'] = Variant('a(uu)', [[0, 0]]) # allowed mode none, preferred mode none MM_MODEM_MODE_NONE
            self.props['CurrentModes'] = Variant('(uu)', [0, 0]) # allowed mode none, preferred mode none MM_MODEM_MODE_NONE

        self.props['EquipmentIdentifier'] = Variant('s', self.ofono_props['Serial'].value if 'Serial' in self.ofono_props else '')
        self.props['HardwareRevision'] = Variant('s', self.ofono_props['Revision'].value if 'Revision' in self.ofono_props else '')
        self.props['Revision'] = Variant('s', self.ofono_props['SoftwareVersionNumber'].value if 'SoftwareVersionNumber' in self.ofono_props else '')
        self.props['Manufacturer'] = Variant('s', self.ofono_props['Manufacturer'].value if 'Manufacturer' in self.ofono_props else 'ofono')
        self.props['Model'] = Variant('s', self.ofono_props['Model'].value if 'Model' in self.ofono_props else 'binder')

        if old_state != self.props['State'].value:
            self.StateChanged(old_state, self.props['State'].value, 1)

        changed_props = {}
        for prop in self.props:
            if self.props[prop].value != old_props[prop].value:
                changed_props.update({ prop: self.props[prop].value })

        self.emit_properties_changed(changed_props)

    @method()
    async def Enable(self, enable: 'b'):
        if self.props['State'].value == -1:
            return

        old_state = self.props['State'].value
        self.props['State'] = Variant('i', 6 if enable else 3)
        self.StateChanged(old_state, self.props['State'].value, 1)
        self.emit_properties_changed({'State': self.props['State'].value})

        try:
            await self.ofono_modem.call_set_property('Online', Variant('b', enable))
        except Exception as e:
            pass

        self.set_props()

    @method()
    def ListBearers(self) -> 'ao':
        return self.props['Bearers'].value

    @method()
    async def CreateBearer(self, properties: 'a{sv}') -> 'o':
        try:
            return await self.doCreateBearer(properties)
        except Exception as e:
            pass

    async def doCreateBearer(self, properties):
        global bearer_i

        if 'org.ofono.ConnectionManager' not in self.ofono_interfaces:
            return

        # print(f"docreatebearer {bearer_i}" )
        mm_bearer_interface = MMBearerInterface(self.index, self.bus, self.ofono_client, self.modem_name, self.ofono_modem, self.ofono_props, self.ofono_interfaces, self.ofono_interface_props, self)
        mm_bearer_interface.props.update({
            "Properties": Variant('a{sv}', properties)
        })

        if 'org.ofono.ConnectionManager' in self.ofono_interfaces:
            # users would usually have to do
            # set-context-property 0 AccessPointName example.apn && activate-context 1
            # to activate the correct context for ofono2mm to use, lets do it on bearer creation to not need ofono scripts
            contexts = await self.ofono_interfaces['org.ofono.ConnectionManager'].call_get_contexts()
            self.context_names = []
            ctx_idx = 0
            chosen_apn = None
            chosen_ctx_path = None
            for ctx in contexts:
                name = ctx[1].get('Type', Variant('s', '')).value
                access_point_name = ctx[1].get('AccessPointName', Variant('s', '')).value
                if name.lower() == "internet":
                    ctx_idx += 1
                    if access_point_name:
                        self.context_names.append(access_point_name)
                        chosen_apn = access_point_name
                        chosen_ctx_path = ctx[0]

                        # print(chosen_ctx_path)

                if chosen_ctx_path:
                    # print("set apn")
                    chosen_ctx_interface = self.ofono_client["ofono_context"][chosen_ctx_path]['org.ofono.ConnectionContext']
                    await chosen_ctx_interface.call_set_property("Active", Variant('b', False))
                    await chosen_ctx_interface.call_set_property("AccessPointName", Variant('s', chosen_apn))
                    await chosen_ctx_interface.call_set_property("Protocol", Variant('s', 'ip'))
                    await chosen_ctx_interface.call_set_property("Active", Variant('b', True))

        ofono_ctx = await self.ofono_interfaces['org.ofono.ConnectionManager'].call_add_context("internet")
        ofono_ctx_interface = self.ofono_client["ofono_context"][ofono_ctx]['org.ofono.ConnectionContext']
        if 'apn' in properties:
            await ofono_ctx_interface.call_set_property("AccessPointName", properties['apn'])

        await mm_bearer_interface.add_auth_ofono(properties['username'].value if 'username' in properties else '',
                                                        properties['password'].value if 'password' in properties else '')

        await ofono_ctx_interface.call_set_property("Protocol", Variant('s', 'ip'))
        mm_bearer_interface.ofono_ctx = ofono_ctx
        self.bus.export(f'/org/freedesktop/ModemManager/Bearer/{bearer_i}', mm_bearer_interface)
        self.props['Bearers'].value.append(f'/org/freedesktop/ModemManager/Bearer/{bearer_i}')
        self.bearers[f'/org/freedesktop/ModemManager/Bearer/{bearer_i}'] = mm_bearer_interface
        self.emit_properties_changed({'Bearers': self.props['Bearers'].value})
        bearer_i += 1

        return f'/org/freedesktop/ModemManager/Bearer/{bearer_i}'

    @method()
    async def DeleteBearer(self, path: 'o'):
        if path in self.props['Bearers'].value:
            self.props['Bearers'].value.remove(path)
            await self.ofono_interfaces['org.ofono.ConnectionManager'].call_remove_context(self.bearers[path].ofono_ctx)
            self.bearers.pop(path)
            self.bus.unexport(path)
            self.emit_properties_changed({'Bearers': self.props['Bearers'].value})

    @method()
    async def Reset(self):
        await self.ofono_modem.call_set_property('Powered', Variant('b', False))
        await self.ofono_modem.call_set_property('Powered', Variant('b', True))

        old_state = self.props['State'].value
        self.props['State'] = Variant('i', 6)  # 6 typically represents an enabled state
        self.StateChanged(old_state, self.props['State'].value, 1)
        self.emit_properties_changed({'State': self.props['State'].value})

        await self.ofono_modem.call_set_property('Online', Variant('b', True))

        self.set_props()

    @method()
    async def FactoryReset(self, code: 's'):
        # not quite a factory reset but better than nothing
        await self.ofono_modem.call_set_property('Powered', Variant('b', False))
        await self.ofono_modem.call_set_property('Powered', Variant('b', True))

        old_state = self.props['State'].value
        self.props['State'] = Variant('i', 6)  # 6 typically represents an enabled state
        self.StateChanged(old_state, self.props['State'].value, 1)
        self.emit_properties_changed({'State': self.props['State'].value})

        await self.ofono_modem.call_set_property('Online', Variant('b', True))

        self.set_props()

    @method()
    async def SetPowerState(self, state: 'u'):
        if state == 1:
            await self.ofono_modem.call_set_property('Powered', Variant('b', False))

        if state in [2, 3]:  # If state is 'on' or 'low'
            await self.ofono_modem.call_set_property('Powered', Variant('b', True))

            old_state = self.props['State'].value
            self.props['State'] = Variant('i', 6)  # 6 typically represents an enabled state
            self.StateChanged(old_state, self.props['State'].value, 1)
            self.emit_properties_changed({'State': self.props['State'].value})

            await self.ofono_modem.call_set_property('Online', Variant('b', True))

            self.set_props()

    @method()
    def SetCurrentCapabilities(self, capabilities: 'u'):
        self.props['CurrentCapabilities'] = Variant('u', capabilities)

    @method()
    async def SetCurrentModes(self, modes: '(uu)'):
        if modes in self.props['SupportedModes'].value:
            if modes[1] == 16:
                await self.ofono_interfaces['org.ofono.RadioSettings'].call_set_property('TechnologyPreference', Variant('s', 'nr'))
            if modes[1] == 8:
                await self.ofono_interfaces['org.ofono.RadioSettings'].call_set_property('TechnologyPreference', Variant('s', 'lte'))
            if modes[1] == 4:
                await self.ofono_interfaces['org.ofono.RadioSettings'].call_set_property('TechnologyPreference', Variant('s', 'umts'))
            if modes[1] == 0:
                if modes[0] | 2:
                    await self.ofono_interfaces['org.ofono.RadioSettings'].call_set_property('TechnologyPreference', Variant('s', 'gsm'))
                elif modes[0] | 4:
                    await self.ofono_interfaces['org.ofono.RadioSettings'].call_set_property('TechnologyPreference', Variant('s', 'umts'))
                elif modes[0] | 8:
                    await self.ofono_interfaces['org.ofono.RadioSettings'].call_set_property('TechnologyPreference', Variant('s', 'lte'))
                elif modes[0] | 16:
                    await self.ofono_interfaces['org.ofono.RadioSettings'].call_set_property('TechnologyPreference', Variant('s', 'nr'))

        self.set_props()

    @method()
    def SetCurrentBands(self, bands: 'au'):
        self.props['CurrentBands'] = Variant('u', bands)

    @method()
    def SetPrimarySimSlot(self, sim_slot: 'u'):
        self.props['PrimarySimSlot'] = Variant('u', sim_slot)

    @method()
    def GetCellInfo(self) -> 'aa{sv}':
        cell_info = {
            "cell-type": Variant("u", self.mm_cell_type),
            "serving": Variant("b", self.props['State'].value == 8), # 8 should mean its registered correctly to a network
        }

        return [cell_info]

    @method()
    def Command(self, cmd: 's', timeout: 'u') -> 's':
        return ''

    @signal()
    def StateChanged(self, old, new, reason) -> 'iiu':
        return [old, new, reason]

    @dbus_property(access=PropertyAccess.READ)
    def Sim(self) -> 'o':
        return self.props['Sim'].value

    @dbus_property(access=PropertyAccess.READ)
    def SimSlots(self) -> 'ao':
        return self.props['SimSlots'].value

    @dbus_property(access=PropertyAccess.READ)
    def PrimarySimSlot(self) -> 'u':
        return self.props['PrimarySimSlot'].value

    @dbus_property(access=PropertyAccess.READ)
    def Bearers(self) -> 'ao':
        return self.props['Bearers'].value

    @dbus_property(access=PropertyAccess.READ)
    def SupportedCapabilities(self) -> 'au':
        return self.props['SupportedCapabilities'].value

    @dbus_property(access=PropertyAccess.READ)
    def CurrentCapabilities(self) -> 'u':
        return self.props['CurrentCapabilities'].value

    @dbus_property(access=PropertyAccess.READ)
    def MaxBearers(self) -> 'u':
        return self.props['MaxBearers'].value

    @dbus_property(access=PropertyAccess.READ)
    def MaxActiveBearers(self) -> 'u':
        return self.props['MaxActiveBearers'].value

    @dbus_property(access=PropertyAccess.READ)
    def MaxActiveMultiplexedBearers(self) -> 'u':
        return self.props['MaxActiveMultiplexedBearers'].value

    @dbus_property(access=PropertyAccess.READ)
    def Manufacturer(self) -> 's':
        return self.props['Manufacturer'].value

    @dbus_property(access=PropertyAccess.READ)
    def Model(self) -> 's':
        return self.props['Model'].value

    @dbus_property(access=PropertyAccess.READ)
    def Revision(self) -> 's':
        return self.props['Revision'].value

    @dbus_property(access=PropertyAccess.READ)
    def HardwareRevision(self) -> 's':
        return self.props['HardwareRevision'].value

    @dbus_property(access=PropertyAccess.READ)
    def DeviceIdentifier(self) -> 's':
        return self.props['DeviceIdentifier'].value

    @dbus_property(access=PropertyAccess.READ)
    def Device(self) -> 's':
        return self.props['Device'].value

    @dbus_property(access=PropertyAccess.READ)
    def Physdev(self) -> 's':
        return self.props['Physdev'].value

    @dbus_property(access=PropertyAccess.READ)
    def Drivers(self) -> 'as':
        return self.props['Drivers'].value

    @dbus_property(access=PropertyAccess.READ)
    def Plugin(self) -> 's':
        return self.props['Plugin'].value

    @dbus_property(access=PropertyAccess.READ)
    def PrimaryPort(self) -> 's':
        return self.props['PrimaryPort'].value

    @dbus_property(access=PropertyAccess.READ)
    def Ports(self) -> 'a(su)':
        return self.props['Ports'].value

    @dbus_property(access=PropertyAccess.READ)
    def EquipmentIdentifier(self) -> 's':
        return self.props['EquipmentIdentifier'].value

    @dbus_property(access=PropertyAccess.READ)
    def UnlockRequired(self) -> 'u':
        return self.props['UnlockRequired'].value

    @dbus_property(access=PropertyAccess.READ)
    def UnlockRetries(self) -> 'a{uu}':
        return self.props['UnlockRetries'].value

    @dbus_property(access=PropertyAccess.READ)
    def State(self) -> 'i':
        return self.props['State'].value

    @dbus_property(access=PropertyAccess.READ)
    def StateFailedReason(self) -> 'u':
        return self.props['StateFailedReason'].value

    @dbus_property(access=PropertyAccess.READ)
    def AccessTechnologies(self) -> 'u':
        return self.props['AccessTechnologies'].value

    @dbus_property(access=PropertyAccess.READ)
    def SignalQuality(self) -> '(ub)':
        return self.props['SignalQuality'].value

    @dbus_property(access=PropertyAccess.READ)
    def OwnNumbers(self) -> 'as':
        return self.props['OwnNumbers'].value

    @dbus_property(access=PropertyAccess.READ)
    def PowerState(self) -> 'u':
        return self.props['PowerState'].value

    @dbus_property(access=PropertyAccess.READ)
    def SupportedModes(self) -> 'a(uu)':
        return self.props['SupportedModes'].value

    @dbus_property(access=PropertyAccess.READ)
    def CurrentModes(self) -> '(uu)':
        return self.props['CurrentModes'].value

    @dbus_property(access=PropertyAccess.READ)
    def SupportedBands(self) -> 'au':
        return self.props['SupportedBands'].value

    @dbus_property(access=PropertyAccess.READ)
    def CurrentBands(self) -> 'au':
        return self.props['CurrentBands'].value

    @dbus_property(access=PropertyAccess.READ)
    def SupportedIpFamilies(self) -> 'u':
        return self.props['SupportedIpFamilies'].value

    def ofono_changed(self, name, varval):
        self.ofono_props[name] = varval
        if name == "Interfaces":
            for iface in varval.value:
                if not (iface in self.ofono_interfaces):
                    self.loop.create_task(self.add_ofono_interface(iface))
            for iface in self.ofono_interfaces:
                if not (iface in varval.value):
                    self.loop.create_task(self.remove_ofono_interface(iface))

        self.set_props()
        if self.mm_modem3gpp_interface:
            self.mm_modem3gpp_interface.ofono_changed(name, varval)
        if self.mm_sim_interface:
            self.mm_sim_interface.ofono_changed(name, varval)

    def ofono_interface_changed(self, iface):
        def ch(name, varval):
            if iface in self.ofono_interface_props:
                self.ofono_interface_props[iface][name] = varval
                self.set_props()
                if self.mm_modem3gpp_interface:
                    self.mm_modem3gpp_interface.ofono_interface_changed(iface)(name, varval)
                if self.mm_sim_interface:
                    self.mm_sim_interface.ofono_interface_changed(iface)(name, varval)

        return ch
