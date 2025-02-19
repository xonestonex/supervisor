"""Test Network Manager Connection object."""
import asyncio
from typing import Any
from unittest.mock import patch

from dbus_fast.aio.proxy_object import ProxyInterface
from dbus_fast.signature import Variant

from supervisor.coresys import CoreSys
from supervisor.dbus.network.setting.generate import get_connection_from_interface
from supervisor.host.const import InterfaceMethod
from supervisor.host.network import Interface
from supervisor.utils.dbus import DBus

from tests.common import fire_watched_signal
from tests.const import TEST_INTERFACE

SETTINGS_WITH_SIGNATURE = {
    "connection": {
        "id": Variant("s", "Wired connection 1"),
        "interface-name": Variant("s", "eth0"),
        "permissions": Variant("as", []),
        "timestamp": Variant("t", 1598125548),
        "type": Variant("s", "802-3-ethernet"),
        "uuid": Variant("s", "0c23631e-2118-355c-bbb0-8943229cb0d6"),
    },
    "ipv4": {
        "address-data": Variant(
            "aa{sv}",
            [
                {
                    "address": Variant("s", "192.168.2.148"),
                    "prefix": Variant("u", 24),
                }
            ],
        ),
        "addresses": Variant("aau", [[2483202240, 24, 16951488]]),
        "dns": Variant("au", [16951488]),
        "dns-search": Variant("as", []),
        "gateway": Variant("s", "192.168.2.1"),
        "method": Variant("s", "auto"),
        "route-data": Variant(
            "aa{sv}",
            [
                {
                    "dest": Variant("s", "192.168.122.0"),
                    "prefix": Variant("u", 24),
                    "next-hop": Variant("s", "10.10.10.1"),
                }
            ],
        ),
        "routes": Variant("aau", [[8038592, 24, 17435146, 0]]),
    },
    "ipv6": {
        "address-data": Variant("aa{sv}", []),
        "addresses": Variant("a(ayuay)", []),
        "dns": Variant("au", []),
        "dns-search": Variant("as", []),
        "method": Variant("s", "auto"),
        "route-data": Variant("aa{sv}", []),
        "routes": Variant("aau", []),
        "addr-gen-mode": Variant("i", 0),
    },
    "proxy": {},
    "802-3-ethernet": {
        "auto-negotiate": Variant("b", False),
        "mac-address-blacklist": Variant("as", []),
        "s390-options": Variant("a{ss}", {}),
    },
    "802-11-wireless": {"ssid": Variant("ay", bytes([78, 69, 84, 84]))},
}


async def mock_call_dbus_get_settings_signature(
    _: ProxyInterface, method: str, *args, unpack_variants: bool = True
) -> list[dict[str, Any]]:
    """Call dbus method mock for get settings that keeps signature."""
    if method == "call_get_settings" and not unpack_variants:
        return SETTINGS_WITH_SIGNATURE
    else:
        assert method == "call_update"
        settings = args[0]

        assert "connection" in settings
        assert settings["connection"]["id"] == Variant("s", "Supervisor eth0")
        assert settings["connection"]["interface-name"] == Variant("s", "eth0")
        assert settings["connection"]["uuid"] == Variant(
            "s", "0c23631e-2118-355c-bbb0-8943229cb0d6"
        )
        assert settings["connection"]["autoconnect"] == Variant("b", True)

        assert "ipv4" in settings
        assert settings["ipv4"]["method"] == Variant("s", "auto")
        assert "gateway" not in settings["ipv4"]
        assert "dns" not in settings["ipv4"]
        assert "address-data" not in settings["ipv4"]
        assert "addresses" not in settings["ipv4"]
        assert len(settings["ipv4"]["route-data"].value) == 1
        assert settings["ipv4"]["route-data"].value[0]["dest"] == Variant(
            "s", "192.168.122.0"
        )
        assert settings["ipv4"]["route-data"].value[0]["prefix"] == Variant("u", 24)
        assert settings["ipv4"]["route-data"].value[0]["next-hop"] == Variant(
            "s", "10.10.10.1"
        )
        assert settings["ipv4"]["routes"] == Variant(
            "aau", [[8038592, 24, 17435146, 0]]
        )

        assert "ipv6" in settings
        assert settings["ipv6"]["method"] == Variant("s", "auto")
        assert "gateway" not in settings["ipv6"]
        assert "dns" not in settings["ipv6"]
        assert "address-data" not in settings["ipv6"]
        assert "addresses" not in settings["ipv6"]
        assert settings["ipv6"]["addr-gen-mode"] == Variant("i", 0)

        assert "proxy" in settings

        assert "802-3-ethernet" in settings
        assert settings["802-3-ethernet"]["auto-negotiate"] == Variant("b", False)

        assert "802-11-wireless" in settings
        assert settings["802-11-wireless"]["ssid"] == Variant(
            "ay", bytes([78, 69, 84, 84])
        )
        assert "mode" not in settings["802-11-wireless"]
        assert "powersave" not in settings["802-11-wireless"]

        assert "802-11-wireless-security" not in settings
        assert "vlan" not in settings


async def test_update(coresys: CoreSys):
    """Test network manager update."""
    await coresys.dbus.network.interfaces[TEST_INTERFACE].connect(coresys.dbus.bus)
    interface = Interface.from_dbus_interface(
        coresys.dbus.network.interfaces[TEST_INTERFACE]
    )
    conn = get_connection_from_interface(
        interface,
        name=coresys.dbus.network.interfaces[TEST_INTERFACE].settings.connection.id,
        uuid=coresys.dbus.network.interfaces[TEST_INTERFACE].settings.connection.uuid,
    )

    with patch.object(
        DBus,
        "call_dbus",
        new=mock_call_dbus_get_settings_signature,
    ):
        await coresys.dbus.network.interfaces[TEST_INTERFACE].settings.update(conn)


async def test_ipv6_disabled_is_link_local(coresys: CoreSys):
    """Test disabled equals link local for ipv6."""
    await coresys.dbus.network.interfaces[TEST_INTERFACE].connect(coresys.dbus.bus)
    interface = Interface.from_dbus_interface(
        coresys.dbus.network.interfaces[TEST_INTERFACE]
    )
    interface.ipv4.method = InterfaceMethod.DISABLED
    interface.ipv6.method = InterfaceMethod.DISABLED
    conn = get_connection_from_interface(
        interface,
        name=coresys.dbus.network.interfaces[TEST_INTERFACE].settings.connection.id,
        uuid=coresys.dbus.network.interfaces[TEST_INTERFACE].settings.connection.uuid,
    )

    assert conn["ipv4"]["method"] == Variant("s", "disabled")
    assert conn["ipv6"]["method"] == Variant("s", "link-local")


async def test_watching_updated_signal(coresys: CoreSys, dbus: list[str]):
    """Test get settings called on update signal."""
    await coresys.dbus.network.interfaces[TEST_INTERFACE].connect(coresys.dbus.bus)
    dbus.clear()

    fire_watched_signal(
        coresys.dbus.network.interfaces[TEST_INTERFACE].settings,
        "org.freedesktop.NetworkManager.Settings.Connection.Updated",
        [],
    )
    await asyncio.sleep(0)
    assert dbus == [
        "/org/freedesktop/NetworkManager/Settings/1-org.freedesktop.NetworkManager.Settings.Connection.GetSettings"
    ]
