from dbus_next.service import ServiceInterface, method, dbus_property, signal
from dbus_next.constants import PropertyAccess
from dbus_next import Variant, DBusError
from datetime import datetime
import gi
gi.require_version('Geoclue', '2.0')
from gi.repository import Geoclue

class MMModemLocationInterface(ServiceInterface):
    def __init__(self):
        super().__init__('org.freedesktop.ModemManager1.Modem.Location')
        utc_time = datetime.utcnow().isoformat()

        self.location = {
            2: Variant('a{sv}', {
                'utc-time': Variant('s', utc_time),
                'latitude': Variant('d', 0),
                'longitude': Variant('d', 0),
                'altitude': Variant('d', 0)
            })
        }

        self.props = {
            'Capabilities': Variant('u', 0), # hardcoded dummy value none MM_MODEM_LOCATION_SOURCE_NONE
            'SupportedAssistanceData': Variant('u', 0), # hardcoded dummy value none MM_MODEM_LOCATION_ASSISTANCE_DATA_TYPE_NONE
            'Enabled': Variant('u', 2), # hardcoded dummy value raw MM_MODEM_LOCATION_SOURCE_GPS_RAW
            'SignalsLocation': Variant('b', False),
            'SuplServer': Variant('s', ''),
            'AssistanceDataServers': Variant('as', []),
            'GpsRefreshRate': Variant('u', 30)
        }

    @method()
    def Setup(self, sources: 'u', signal_location: 'b') -> None:
        self.props['Enabled'] = Variant('u', sources)
        self.props['SignalsLocation'] = Variant('b', signal_location)

    @method()
    async def GetLocation(self) -> 'a{uv}':
        geoclue = Geoclue.Simple.new_sync('ModemManager', Geoclue.AccuracyLevel.NEIGHBORHOOD, None)
        location = geoclue.get_location()

        # geoclue has issues, it returns lat and long in place of each other
        longitude = location.get_property('latitude')
        latitude = location.get_property('longitude')
        altitude = location.get_property('altitude')
        utc_time = datetime.utcnow().isoformat()

        self.location = {
            2: Variant('a{sv}', { # 2 is MM_MODEM_LOCATION_SOURCE_GPS_RAW
                'utc-time': Variant('s', utc_time),
                'latitude': Variant('d', latitude),
                'longitude': Variant('d', longitude),
                'altitude': Variant('d', altitude)
            })
        }

        return self.location

    @method()
    def SetSuplServer(self, supl: 's') -> None:
        raise DBusError('org.freedesktop.ModemManager1.Error.Core.Unsupported', f'Cannot set SUPL server: A-GPS not supported')

    @method()
    def InjectAssistanceData(self, data: 'ay') -> None:
        raise DBusError('org.freedesktop.ModemManager1.Error.Core.Unsupported', f'Cannot inject assistance data: ununsupported')

    @method()
    def SetGpsRefreshRate(self, rate: 'u') -> None:
        self.props['GpsRefreshRate'] = Variant('u', rate)

    @dbus_property(access=PropertyAccess.READ)
    def Capabilities(self) -> 'u':
        return self.props['Capabilities'].value

    @dbus_property(access=PropertyAccess.READ)
    def SupportedAssistanceData(self) -> 'u':
        return self.props['SupportedAssistanceData'].value

    @dbus_property(access=PropertyAccess.READ)
    def Enabled(self) -> 'u':
        return self.props['Enabled'].value

    @dbus_property(access=PropertyAccess.READ)
    def SignalsLocation(self) -> 'b':
        return self.props['SignalsLocation'].value

    @dbus_property(access=PropertyAccess.READ)
    def Location(self) -> 'a{uv}':
        return self.location

    @dbus_property(access=PropertyAccess.READ)
    def SuplServer(self) -> 's':
        return self.props['SuplServer'].value

    @dbus_property(access=PropertyAccess.READ)
    def AssistanceDataServers(self) -> 'as':
        return self.props['AssistanceDataServers'].value

    @dbus_property(access=PropertyAccess.READ)
    def GpsRefreshRate(self) -> 'u':
        return self.props['GpsRefreshRate'].value
