from dbus_next.service import ServiceInterface, method, dbus_property, signal
from dbus_next.constants import PropertyAccess
from dbus_next import Variant

from ofono2mm.mm_types import ModemManagerCallState

class MMCallInterface(ServiceInterface):
    def __init__(self, index, bus, ofono_client, modem_name, ofono_modem, ofono_props, ofono_interfaces, ofono_interface_props):
        super().__init__('org.freedesktop.ModemManager1.Call')
        self.index = index
        self.bus = bus
        self.ofono_client = ofono_client
        self.ofono_proxy = self.ofono_client["ofono_modem"][modem_name]
        self.modem_name = modem_name
        self.ofono_modem = ofono_modem
        self.ofono_props = ofono_props
        self.ofono_interfaces = ofono_interfaces
        self.ofono_interface_props = ofono_interface_props
        self.voicecall = '/'
        self.props = {
            'State': Variant('u', ModemManagerCallState.UNKNOWN),
            'StateReason': Variant('u', 0), # on runtime unknown MM_CALL_STATE_REASON_UNKNOWN
            'Direction': Variant('u', 0), # on runtime unknown MM_CALL_DIRECTION_UNKNOWN
            'Number': Variant('s', ''),
            'Multiparty': Variant('b', False),
            'AudioPort': Variant('s', ''),
            'AudioFormat': Variant('a{sv}', {
                "encoding": Variant('s', 'pcm'),
                "resolution": Variant('s', 's16le'),
                "rate": Variant('u', 48000),
            })
        }

    @method()
    def Start(self):
        self.props['State'] = Variant('u', ModemManagerCallState.ACTIVE)
        self.props['StateReason'] = Variant('u', 1) # accepted MM_CALL_STATE_REASON_OUTGOING_STARTED

    @method()
    async def Accept(self):
        ofono_interface = self.ofono_client["ofono_modem"][self.voicecall]['org.ofono.VoiceCall']
        await ofono_interface.call_answer()
        self.props['State'] = Variant('u', ModemManagerCallState.ACTIVE)
        self.props['StateReason'] = Variant('u', 3) # accepted MM_CALL_STATE_REASON_ACCEPTED

    @method()
    async def Deflect(self, number: 's'):
        ofono_interface = self.ofono_client["ofono_modem"][self.voicecall]['org.ofono.VoiceCall']
        await ofono_interface.call_deflect(number)
        self.props['StateReason'] = Variant('u', 10) # deflected MM_CALL_STATE_REASON_DEFLECTED

    @method()
    async def JoinMultiparty(self):
        await self.ofono_interfaces['org.ofono.VoiceCallManager'].call_create_multiparty()
        self.props['Multiparty'] = Variant('b', True)

    @method()
    async def LeaveMultiparty(self):
        await self.ofono_interfaces['org.ofono.VoiceCallManager'].call_hangup_multiparty()
        self.props['Multiparty'] = Variant('b', False)

    @method()
    async def Hangup(self):
        # ofono_interface = self.ofono_client["ofono_modem"][self.voicecall]['org.ofono.VoiceCall']
        # await ofono_interface.call_hangup()
        await self.ofono_interfaces['org.ofono.VoiceCallManager'].call_hangup_all()
        self.props['State'] = Variant('u', ModemManagerCallState.TERMINATED)
        self.props['StateReason'] = Variant('u', 4) # terminated MM_CALL_STATE_REASON_TERMINATED

    @method()
    async def SendDtmf(self, dtmf: 's'):
        await self.ofono_interfaces['org.ofono.VoiceCallManager'].call_send_tones(dtmf)

    @signal()
    def DtmfReceived(self, dtmf) -> 's':
        return dtmf

    @signal()
    def StateChanged(self, old, new, reason) -> 'iiu':
        return [old, new, reason]

    @dbus_property(access=PropertyAccess.READ)
    def State(self) -> 'i':
        return self.props['State'].value

    @dbus_property(access=PropertyAccess.READ)
    def StateReason(self) -> 'i':
        return self.props['StateReason'].value

    @dbus_property(access=PropertyAccess.READ)
    def Direction(self) -> 'i':
        return self.props['Direction'].value

    @dbus_property(access=PropertyAccess.READ)
    def Number(self) -> 's':
        return self.props['Number'].value

    @dbus_property(access=PropertyAccess.READ)
    def Multiparty(self) -> 'b':
        return self.props['Multiparty'].value

    @dbus_property(access=PropertyAccess.READ)
    def AudioPort(self) -> 's':
        return self.props['AudioPort'].value

    @dbus_property(access=PropertyAccess.READ)
    def AudioFormat(self) -> 'a{sv}':
        return self.props['AudioFormat'].value
