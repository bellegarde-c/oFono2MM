#!/usr/bin/env python3

from dbus_next.aio import MessageBus
from dbus_next.service import (ServiceInterface,
                               method, dbus_property)
from dbus_next.constants import PropertyAccess
from dbus_next import DBusError, BusType
import asyncio
from ofono2mm import MMModemInterface, Ofono, DBus
from ofono2mm.utils import async_locked

has_bus = False
sim_i = 0

class MMInterface(ServiceInterface):
    def __init__(self, loop, bus):
        super().__init__('org.freedesktop.ModemManager1')
        self.loop = loop
        self.bus = bus
        self.ofono_client = Ofono(bus)
        self.dbus_client = DBus(bus)
        self.mm_modem_interfaces = []
        self.mm_modem_objects = []
        self.offline_modems = []
        self.loop.create_task(self.check_ofono_presence())

    @dbus_property(access=PropertyAccess.READ)
    def Version(self) -> 's':
        return '1.22.0'

    @method()
    async def ScanDevices(self):
        try:
            await self.find_ofono_modems()
        except Exception as e:
            pass

    async def check_ofono_presence(self):
        dbus_iface = self.dbus_client["dbus"]["/org/freedesktop/DBus"]["org.freedesktop.DBus"]
        dbus_iface.on_name_owner_changed(self.dbus_name_owner_changed)
        has_ofono = await dbus_iface.call_name_has_owner("org.ofono")
        if has_ofono:
            self.ofono_added()
        else:
            self.ofono_removed()

    def ofono_added(self):
        self.ofono_manager_interface = self.ofono_client["ofono"]["/"]["org.ofono.Manager"]
        self.ofono_manager_interface.on_modem_added(self.ofono_modem_added)
        self.ofono_manager_interface.on_modem_removed(self.ofono_modem_removed)
        self.loop.create_task(self.find_ofono_modems())

    def ofono_removed(self):
        self.ofono_manager_interface = None

    @async_locked
    async def find_ofono_modems(self):
        global has_bus, sim_i

        for mm_object in self.mm_modem_objects:
            self.bus.unexport(mm_object)

        self.mm_modem_objects = []
        self.mm_modem_interfaces = []
        self.offline_modems = []

        if not self.ofono_manager_interface:
            return

        self.ofono_modem_list = False
        while not self.ofono_modem_list:
            try:
                self.ofono_modem_list = [
                    x
                    for x in await self.ofono_manager_interface.call_get_modems()
                    if x[0].startswith("/ril_") # FIXME
                ]
            except DBusError:
                pass

        self.i = 0
        sim_i = len(self.ofono_modem_list)

        for modem in self.ofono_modem_list:
            self.ofono_sim_manager = self.ofono_client["ofono_modem"][modem[0]]['org.ofono.SimManager']
            sim_manager_props = await self.ofono_sim_manager.call_get_properties()
            sim_present = sim_manager_props['Present'].value

            #print(f"modem is {modem[0]}, online: {modem[1]['Online'].value}, number of sims: {sim_i} sim is present: {sim_present}")

            if sim_present == False and sim_i > 1:
                self.offline_modems.append(modem)
            else:
                await self.export_new_modem(modem[0], modem[1])

        for modem_info in self.offline_modems:
            await self.export_new_modem(*modem_info)

        if not has_bus and len(self.mm_modem_objects) != 0:
            await self.bus.request_name('org.freedesktop.ModemManager1')
            has_bus = True

    def dbus_name_owner_changed(self, name, old_owner, new_owner):
        if name == "org.ofono":
            if new_owner == "":
                self.ofono_removed()
            elif old_owner == "":
                self.ofono_added()

    def ofono_modem_added(self, path, mprops):
        try:
            self.loop.create_task(self.export_new_modem(path, mprops))
        except Exception as e:
            pass

    async def export_new_modem(self, path, mprops):
        mm_modem_interface = MMModemInterface(self.loop, self.i, self.bus, self.ofono_client, path)
        mm_modem_interface.ofono_props = mprops
        self.ofono_client["ofono_modem"][path]['org.ofono.Modem'].on_property_changed(mm_modem_interface.ofono_changed)
        await mm_modem_interface.init_ofono_interfaces()

        #print(f"Processing modem: {path}")
        self.bus.export(f'/org/freedesktop/ModemManager1/Modem/{self.i}', mm_modem_interface)
        mm_modem_interface.set_props()
        await mm_modem_interface.init_mm_sim_interface()
        await mm_modem_interface.init_mm_3gpp_interface()
        await mm_modem_interface.init_mm_3gpp_ussd_interface()
        await mm_modem_interface.init_mm_3gpp_profile_manager_interface()
        await mm_modem_interface.init_mm_messaging_interface()
        await mm_modem_interface.init_mm_simple_interface()
        await mm_modem_interface.init_mm_firmware_interface()
        await mm_modem_interface.init_mm_time_interface()
        await mm_modem_interface.init_mm_cdma_interface()
        await mm_modem_interface.init_mm_sar_interface()
        await mm_modem_interface.init_mm_oma_interface()
        await mm_modem_interface.init_mm_signal_interface()
        await mm_modem_interface.init_mm_location_interface()
        await mm_modem_interface.init_mm_voice_interface()
        self.mm_modem_interfaces.append(mm_modem_interface)
        self.mm_modem_objects.append(f'/org/freedesktop/ModemManager1/Modem/{self.i}')
        self.i += 1

        mm_modem_simple = mm_modem_interface.get_mm_modem_simple_interface()
        try:
            self.loop.create_task(self.simple_set_apn(mm_modem_simple))
        except Exception as e:
            pass

    async def simple_set_apn(self, mm_modem_simple):
        while True:
            ret = await mm_modem_simple.network_manager_set_apn()
            if ret == True:
               return

            await asyncio.sleep(2)

    def ofono_modem_removed(self, path):
        for mm_object in self.mm_modem_objects:
            try:
                if mm_object.modem_name == path:
                    self.bus.unexport(mm_object)
            except Exception as e:
                pass

    @method()
    def SetLogging(self, level: 's'):
        pass

    @method()
    def ReportKernelEvent(self, properties: 'a{sv}'):
        pass

    @method()
    def InhibitDevice(self, uid: 's', inhibit: 'b'):
        pass

async def main():
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    loop = asyncio.get_running_loop()
    mm_manager_interface = MMInterface(loop, bus)
    bus.export('/org/freedesktop/ModemManager1', mm_manager_interface)
    await bus.wait_for_disconnect()

asyncio.run(main())
