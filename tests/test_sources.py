"""Parser and adapter tests. No network: every input is an inline string or a fixture file."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from app.sources import bts_delay_cause as dc
from app.sources.bts_ontime import aggregate_month
from app.sources.faa_enplanements import discover_workbooks, parse_workbook
from app.sources.nas_status import parse_nas_status
from app.sources.ourairports import parse_airports, parse_runways, qualifying_runway_counts
from app.sources.taf import build_compact

FIXTURES = Path(__file__).parent / "fixtures"


# ----------------------------------------------------------------------------- FAA
def test_discover_workbooks_prefers_latest_year_and_preliminary_first():
    html = '''<a href="/x/arp-cy2024-all-enplanements.xlsx">a</a>
              <a href="/x/arp-cy2025-all-enplanements-preliminary.xlsx">b</a>
              <a href="/x/arp-cy2024-commercial-service-enplanements.xlsx">c</a>'''
    found = discover_workbooks(html)
    assert found[0] == (2025, True, "https://www.faa.gov/x/arp-cy2025-all-enplanements-preliminary.xlsx")
    assert found[1][0] == 2024 and found[1][1] is False
    assert len(found) == 2  # commercial-service workbook is ignored


def test_parse_workbook_recomputes_growth_and_keeps_service_level_distinct_from_hub(faa):
    frame = faa.frame
    assert faa.latest_year == 2025 and faa.previous_year == 2024 and faa.preliminary is True
    anc = frame[frame["lid"] == "ANC"].iloc[0]
    assert anc["service_level"] == "P" and anc["hub"] == "M"          # S/L vs Hub not swapped
    assert anc["enplanements"] == 2729285 and anc["enplanements_prev"] == 2767856
    assert anc["yoy_pct"] == pytest.approx(-1.39, abs=0.01)           # workbook shows fraction -0.0139
    assert frame["lid"].is_unique
    assert set(frame["service_level"]) >= {"P", "CS", "GA"}


def test_parse_workbook_handles_zero_previous_year():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Rank", "RO", "ST", "Locid", "City", "Airport Name", "S/L", "Hub", "CY 25 Enplanements", "CY 24 Enplanements", "% Change"])
    ws.append([1, "NE", "MA", "XXX", "Town", "Test Field", "CS", "N", 1000, 0, None])
    ws.append([2, "NE", "MA", "YYY", "Town", "Other Field", "P", "S", 5000, 4000, 0.25])
    buf = io.BytesIO()
    wb.save(buf)
    result = parse_workbook(buf.getvalue(), "final.xlsx")
    assert result.preliminary is False
    row = result.frame.set_index("lid")
    assert pd.isna(row.loc["XXX", "yoy_pct"]) and row.loc["YYY", "yoy_pct"] == 25.0


# ------------------------------------------------------------------- BTS delay cause
def test_cipher_round_trip_and_known_page_string():
    assert dc.decode("9ur4r Brn4z106u or69rr0 FHGEM NaQ FHGEM") == "where yearmonth between 24319 AND 24319"
    assert dc.encode(dc.decode("9ur4r Brn4z106u or69rr0 FHGEM NaQ FHGEM")) == "9ur4r Brn4z106u or69rr0 FHGEM NaQ FHGEM"
    assert dc.key_to_month(24319) == (2026, 7) and dc.month_key(2026, 7) == 24319
    assert dc.key_to_month(dc.month_key(2025, 12)) == (2025, 12)


def test_default_window_uses_two_month_lag():
    from datetime import date
    start, end = dc.default_window(date(2026, 9, 27), months=12)
    assert end == (2026, 7) and start == (2025, 8)


def test_parse_delay_cause_aggregates_carriers_per_airport_month():
    csv = (
        "year,month,carrier,carrier_name,airport,airport_name,arr_flights,arr_del15,carrier_ct,weather_ct,nas_ct,security_ct,"
        "late_aircraft_ct,arr_cancelled,arr_diverted,arr_delay,carrier_delay,weather_delay,nas_delay,security_delay,late_aircraft_delay\n"
        "2026,7,AA,American,SFO,\"San Francisco, CA: SFO Intl\",100,30,10,2,15,0,3,1,0,1800,600,100,900,0,200\n"
        "2026,7,UA,United,SFO,\"San Francisco, CA: SFO Intl\",200,50,20,3,20,0,7,3,1,3000,1000,200,1500,0,300\n"
        "2026,7,UA,United,LAX,\"Los Angeles, CA: LAX Intl\",150,20,10,1,5,0,4,2,0,1000,500,50,300,0,150\n"
    ).encode()
    frame = dc.parse_delay_cause_csv(csv)
    sfo = frame[frame["airport"] == "SFO"].iloc[0]
    assert len(frame) == 2 and sfo["arr_flights"] == 300 and sfo["arr_del15"] == 80 and sfo["nas_ct"] == 35
    assert sfo["airport_name"].startswith("San Francisco")


# ------------------------------------------------------------------------ TAF build
def _xlsx_bytes(rows, header):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_build_compact_splits_actual_and_forecast_and_sums_categories():
    enp = _xlsx_bytes([["SFO", 0, 2024, 100, 1, 10, 20, 30], ["SFO", 1, 2025, 110, 1, 11, 22, 33], ["ZZZ", 0, 2024, 5, 0, 0, 0, 0]],
                      ["locid", "scenario", "ayear", "aac", "aat", "commuter", "us_flag", "frgn_flag"])
    ops = _xlsx_bytes([["SFO", 0, 2024, 300, 50, 10, 2, 0, 0, 0], ["SFO", 1, 2025, 310, 52, 10, 2, 0, 0, 0]],
                      ["locid", "scenario", "ayear", "itn_Ac", "itn_at", "itn_ga", "itn_mil", "loc_ga", "loc_mil", "tot_overs"])
    air = _xlsx_bytes([["SFO", 3, 1], ["ZZZ", 0, 0]], ["LOCID", "HUB_SIZE", "OEP35"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Enplanements.xlsx", enp)
        z.writestr("AirportsOperations.xlsx", ops)
        z.writestr("Airports.xlsx", air)
    frame = build_compact(buf.getvalue(), lids={"SFO"})
    assert set(frame["lid"]) == {"SFO"}
    actual = frame[(frame["scenario"] == 0)].iloc[0]
    assert actual["enpl_total"] == 161 and actual["enpl_intl"] == 50 and actual["enpl_domestic"] == 111
    assert actual["ops_air_carrier"] == 300 and actual["hub_size"] == 3 and actual["oep35"] == 1
    assert frame[frame["scenario"] == 1].iloc[0]["year"] == 2025


# --------------------------------------------------------------------- BTS on-time
def test_aggregate_month_builds_routes_and_origin_metrics():
    df = pd.DataFrame({
        "Year": [2026] * 4, "Month": [7] * 4, "Origin": ["ANC", "ANC", "ANC", "SEA"], "Dest": ["SEA", "SEA", "JFK", "ANC"],
        "Distance": [1448.0, 1448.0, 3386.0, 1448.0], "DepDel15": [0.0, 1.0, None, 0.0], "DepDelay": [-3.0, 40.0, None, 0.0],
        "TaxiOut": [12.0, 20.0, None, 15.0], "Cancelled": [0.0, 0.0, 1.0, 0.0], "Diverted": [0.0, 0.0, 0.0, 0.0],
    })
    routes, metrics = aggregate_month(df)
    anc_sea = routes[(routes["origin"] == "ANC") & (routes["dest"] == "SEA")].iloc[0]
    assert anc_sea["departures"] == 2 and anc_sea["distance_mi"] == 1448.0
    anc = metrics[metrics["origin"] == "ANC"].iloc[0]
    assert anc["departures"] == 3 and anc["cancelled"] == 1 and anc["dep_del15"] == 1 and anc["taxi_out_total"] == 32.0 and anc["taxi_out_n"] == 2


# --------------------------------------------------------------------- OurAirports
def test_parse_runways_flags_only_open_long_paved_runways():
    csv = (
        '"id","airport_ref","airport_ident","length_ft","width_ft","surface","lighted","closed","le_ident","le_latitude_deg","le_longitude_deg","le_elevation_ft","le_heading_degT","le_displaced_threshold_ft","he_ident","he_latitude_deg","he_longitude_deg","he_elevation_ft","he_heading_degT","he_displaced_threshold_ft"\n'
        '1,1,"KTST",11000,150,"ASPH",1,0,"10L",,,,,,"28R",,,,,\n'
        '2,1,"KTST",4000,75,"ASPH",1,0,"14",,,,,,"32",,,,,\n'
        '3,1,"KTST",9000,150,"TURF",1,0,"18",,,,,,"36",,,,,\n'
        '4,1,"KTST",9000,150,"CONC",1,1,"01",,,,,,"19",,,,,\n'
        '5,1,"KTST",6000,60,"ASPH",1,0,"H1",,,,,,,,,,,\n'
    ).encode()
    runways = parse_runways(csv)
    assert runways["qualifying"].tolist() == [True, False, False, False, False]
    assert qualifying_runway_counts(runways)["KTST"] == 1


def test_parse_airports_keeps_us_and_territories_and_maps_state():
    csv = (
        '"id","ident","type","name","latitude_deg","longitude_deg","elevation_ft","continent","iso_country","iso_region","municipality","scheduled_service","icao_code","iata_code","gps_code","local_code","home_link","wikipedia_link","keywords"\n'
        '1,"KSFO","large_airport","San Francisco International Airport",37.6,-122.4,13,"NA","US","US-CA","San Francisco","yes","KSFO","SFO","KSFO","SFO","","",""\n'
        '2,"TJSJ","large_airport","Luis Munoz Marin International Airport",18.4,-66.0,9,"NA","PR","PR-U-A","San Juan","yes","TJSJ","SJU","TJSJ","SJU","","",""\n'
        '3,"EGLL","large_airport","London Heathrow Airport",51.4,-0.4,83,"EU","GB","GB-ENG","London","yes","EGLL","LHR","EGLL","","","",""\n'
        '4,"US-0001","heliport","Somewhere Heliport",30.0,-90.0,0,"NA","US","US-LA","Town","no","","","","","","",""\n'
    ).encode()
    airports = parse_airports(csv)
    assert set(airports["ident"]) == {"KSFO", "TJSJ"}
    assert airports.set_index("ident").loc["KSFO", "state"] == "CA"
    assert bool(airports.set_index("ident").loc["KSFO", "scheduled_service"]) is True


# ---------------------------------------------------------------------- NAS status
def test_parse_nas_status_groups_events_by_airport():
    xml = (b"<AIRPORT_STATUS_INFORMATION><Update_Time>Sun Sep 27 15:07:39 2026 GMT</Update_Time>"
           b"<Delay_type><Name>Ground Delay Programs</Name><Ground_Delay_List><Ground_Delay><ARPT>SFO</ARPT><Reason>low ceilings</Reason>"
           b"<Avg>49 minutes</Avg><Max>1 hour and 42 minutes</Max></Ground_Delay></Ground_Delay_List></Delay_type>"
           b"<Delay_type><Name>General Arrival/Departure Delay Info</Name><Arrival_Departure_Delay_List><Delay><ARPT>EWR</ARPT><Reason>OTHER:Bird Strike</Reason>"
           b"<Arrival_Departure Type=\"Departure\"><Min>31 minutes</Min><Max>45 minutes</Max><Trend>Increasing</Trend></Arrival_Departure></Delay></Arrival_Departure_Delay_List></Delay_type>"
           b"<Delay_type><Name>Ground Stop Programs</Name><Ground_Stop_List><Ground_Stop><ARPT>LGA</ARPT><Reason>wind</Reason><End_Time>4:00 pm EDT</End_Time></Ground_Stop></Ground_Stop_List></Delay_type>"
           b"</AIRPORT_STATUS_INFORMATION>")
    parsed = parse_nas_status(xml)
    assert parsed["update_time"].startswith("Sun Sep 27")
    assert parsed["events"]["SFO"][0]["type"] == "ground_delay" and parsed["events"]["SFO"][0]["reason"] == "low ceilings"
    assert parsed["events"]["EWR"][0]["direction"] == "Departure" and parsed["events"]["EWR"][0]["trend"] == "Increasing"
    assert parsed["events"]["LGA"][0]["type"] == "ground_stop"
