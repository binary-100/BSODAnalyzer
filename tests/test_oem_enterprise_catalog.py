"""Tests for enterprise OEM manifest ingestion (Phase A)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import driver_catalog as dc
import oem_enterprise_catalog as oec

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "enterprise_catalog"

LENOVO_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<ModelList version="1.0">
 <Model name="ThinkCentre M715Q" arch="AMD">
  <Types><Type>10M4</Type><Type>10RA</Type></Types>
  <SCCM os="win10" version="1909" date="2020-02-24">https://download.lenovo.com/pccbbs/tc_pack.exe</SCCM>
  <SCCM os="win11" version="23H2" date="2024-06-01">https://download.lenovo.com/pccbbs/tc_win11.exe</SCCM>
 </Model>
</ModelList>
"""

HP_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<HPClientDriverPackCatalog SchemaVersion="1.0.0.0" ToolVersion="1.0" DateReleased="2026-01-01">
<OSList><OS><Name>Windows 11 64-bit, 24H2</Name></OS></OSList>
<SoftPaqList>
  <SoftPaq>
    <Id>sp999001</Id>
    <Name>HP EliteBook 840 G10 Windows 11 Driver Pack</Name>
    <Version>1.0 A 1</Version>
    <Category>Manageability - Driver Pack</Category>
    <DateReleased>2025-01-15</DateReleased>
    <Url>https://ftp.hp.com/pub/softpaq/sp999001.exe</Url>
    <CvaTitle>HP EliteBook 840 G10 Windows 11 Driver Pack</CvaTitle>
  </SoftPaq>
</SoftPaqList>
<ProductOSDriverPackList>
  <ProductOSDriverPack>
    <SystemId>8787</SystemId>
    <SystemName>HP EliteBook 840 G10 Notebook PC</SystemName>
    <OSName>Windows 11 64-bit, 24H2</OSName>
    <SoftPaqId>sp999001</SoftPaqId>
  </ProductOSDriverPack>
</ProductOSDriverPackList>
</HPClientDriverPackCatalog>
"""

DELL_PACK_SNIPPET = b"""<?xml version="1.0"?>
<DriverPackManifest baseLocation="downloads.dell.com" xmlns="openmanage/cm/dm">
  <DriverPackage dellVersion="A02" dateTime="2026-01-01T00:00:00"
    path="FOLDER/1/xps-win11.cab" releaseID="TEST1">
    <Name><Display lang="en">XPS 13 9380 Win11 Pack</Display></Name>
    <SupportedOperatingSystems>
      <OperatingSystem osCode="Windows11" osArch="x64">
        <Display lang="en">Windows 11 x64</Display>
      </OperatingSystem>
    </SupportedOperatingSystems>
    <SupportedSystems>
      <Brand key="72" prefix="XPSNOTEBOOK">
        <Model systemID="08AF" name="XPS 13 9380">
          <Display lang="en">9380</Display>
        </Model>
      </Brand>
    </SupportedSystems>
    <ImportantInfo URL="https://www.dell.com/support/driverId/TEST1"/>
  </DriverPackage>
</DriverPackManifest>
"""


def test_merge_oem_row_lists_dedupes() -> None:
    primary = [{"title": "Realtek Audio", "version": "1.0"}]
    extra = [
        {"title": "Realtek Audio", "version": "1.0"},
        {"title": "Intel Wi-Fi", "version": "2.0"},
    ]
    merged = oec.merge_oem_row_lists(primary, extra)
    assert len(merged) == 2
    assert merged[1]["title"] == "Intel Wi-Fi"


def test_merge_oem_row_lists_enriches_inner_versions() -> None:
    primary = [{"title": "Realtek PCIe Ethernet Controller Driver", "version": "1168.28.1224.2025"}]
    inner = [{"version": "1125.028.1224.2025", "pci": [{"vendor_id": "10EC", "device_id": "8125"}]}]
    extra = [{
        "title": "Realtek PCIe Ethernet Controller Driver",
        "version": "1168.28.1224.2025",
        "inner_versions": inner,
    }]
    merged = oec.merge_oem_row_lists(primary, extra)
    assert len(merged) == 1
    assert merged[0]["inner_versions"] == inner


def test_lenovo_enterprise_rows_from_fixture() -> None:
    with patch.object(oec, "_load_cached_xml", return_value=LENOVO_SAMPLE.encode("utf-8")):
        oec.clear_session_cache()
        ctx = {
            "system_manufacturer": "LENOVO",
            "machine_type": "10M4",
            "system_model": "ThinkCentre M715Q",
        }
        rows = oec.lenovo_enterprise_rows(ctx)
        assert len(rows) == 1
        assert rows[0]["url"].endswith("tc_win11.exe")


def test_hp_enterprise_rows_from_fixture() -> None:
    with patch.object(oec, "_load_cached_xml", return_value=HP_SAMPLE.encode("utf-8")):
        oec.clear_session_cache()
        ctx = {
            "system_manufacturer": "HP",
            "system_model": "HP EliteBook 840 G10 Notebook PC",
            "baseboard_product": "8787",
        }
        rows = oec.hp_enterprise_rows(ctx)
        assert len(rows) >= 1
        assert rows[0]["version"] == "1.0 A 1"
        assert "sp999001" in rows[0]["url"]


def test_dell_pack_catalog_model_match() -> None:
    ctx = {"system_model": "XPS 13 9380", "system_sku": ""}
    rows = oec.parse_dell_driver_pack_catalog_xml(DELL_PACK_SNIPPET, ctx)
    assert len(rows) == 1
    assert rows[0]["version"] == "A02"
    assert "TEST1" in rows[0]["url"]


def test_parse_dell_driver_archive_manifest_from_fixture() -> None:
    sample = (_FIXTURES / "dell_metadata_sample.xml").read_bytes()
    rows = oec._parse_dell_driver_archive_manifest(sample)
    assert rows, "expected Release rows from Dell metadata sample"
    assert any("Killer" in (r.get("title") or "") for r in rows)
    assert any((r.get("version") or "").startswith("12.") for r in rows)


def test_merge_enterprise_oem_rows_wires_dell() -> None:
    with patch.object(
        oec,
        "dell_enterprise_rows",
        return_value=[{"title": "Enterprise NIC", "version": "9.9", "url": "https://dell.example/nic"}],
    ):
        base = [{"title": "Service Tag Audio", "version": "1.0", "url": "https://dell.example/audio"}]
        merged = dc._merge_enterprise_oem_rows(base, {"system_manufacturer": "Dell Inc."}, "dell")
        assert len(merged) == 2


def test_fetch_dell_oem_rows_live_merges_enterprise() -> None:
    api_rows = [{"title": "Dell API Driver", "version": "1.0", "url": "https://dell/api"}]
    ent_rows = [{"title": "Dell Enterprise Driver", "version": "2.0", "url": "https://dell/ent"}]
    with patch.object(dc, "_get_dell_oem_rows_from_api", return_value=list(api_rows)), patch.object(
        dc, "_get_dell_oem_rows_from_local_dup", return_value=[]
    ), patch.object(dc, "_merge_dell_dup_inner_versions_into_rows", side_effect=lambda rows, ctx: rows), patch.object(
        oec, "dell_enterprise_rows", return_value=list(ent_rows)
    ):
        oec.clear_session_cache()
        rows, _ = dc._fetch_dell_oem_rows_live({"system_manufacturer": "Dell Inc."})
        titles = {r["title"] for r in rows}
        assert "Dell API Driver" in titles
        assert "Dell Enterprise Driver" in titles


if __name__ == "__main__":
    test_merge_oem_row_lists_dedupes()
    test_lenovo_enterprise_rows_from_fixture()
    test_hp_enterprise_rows_from_fixture()
    test_dell_pack_catalog_model_match()
    test_parse_dell_driver_archive_manifest_from_fixture()
    test_merge_enterprise_oem_rows_wires_dell()
    test_fetch_dell_oem_rows_live_merges_enterprise()
    print("Enterprise OEM catalog tests OK")
