"""Quick test: discover IBKR scanner parameters for OTC stocks.

Run via: railway run python scripts/test_scanner_params.py
Or locally with TWS: .venv/bin/python scripts/test_scanner_params.py
"""

import asyncio
import xml.etree.ElementTree as ET

from ib_async import IB, ScannerSubscription


async def main():
    ib = IB()

    host = "ib-gateway.railway.internal"
    port = 4003

    print(f"Connecting to {host}:{port}...")
    await ib.connectAsync(host=host, port=port, clientId=99, timeout=15)
    print("Connected!")

    # 1. Get all scanner parameters
    print("\n=== Scanner Parameters (location codes) ===")
    xml_str = await ib.reqScannerParametersAsync()
    root = ET.fromstring(xml_str)

    # Find all location codes
    print("\nLocation codes containing 'US' or 'OTC' or 'PINK':")
    for loc in root.iter("LocationCode"):
        code = loc.text or ""
        if any(x in code.upper() for x in ["US", "OTC", "PINK", "GREY", "MINOR"]):
            print(f"  {code}")

    # Find all scan codes
    print("\nScan codes (first 30):")
    for i, scan in enumerate(root.iter("ScanCode")):
        code = scan.text or ""
        print(f"  {code}")
        if i >= 29:
            print("  ... (truncated)")
            break

    # 2. Try a TRIPS scan
    print("\n=== Test TRIPS Scan ($0.0001-$0.001) ===")
    sub = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US",
        scanCode="MOST_ACTIVE",
        abovePrice=0.0001,
        belowPrice=0.001,
        numberOfRows=10,
    )
    try:
        results = await ib.reqScannerDataAsync(sub)
        print(f"Results: {len(results)}")
        for r in results[:5]:
            c = r.contractDetails.contract
            print(f"  {c.symbol} | exchange={c.exchange} | primaryExchange={c.primaryExchange}")
    except Exception as e:
        print(f"Error: {e}")

    # 3. Try a DUBS scan
    print("\n=== Test DUBS Scan ($0.001-$0.01) ===")
    sub2 = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US",
        scanCode="MOST_ACTIVE",
        abovePrice=0.001,
        belowPrice=0.01,
        numberOfRows=10,
    )
    try:
        results2 = await ib.reqScannerDataAsync(sub2)
        print(f"Results: {len(results2)}")
        for r in results2[:5]:
            c = r.contractDetails.contract
            print(f"  {c.symbol} | exchange={c.exchange} | primaryExchange={c.primaryExchange}")
    except Exception as e:
        print(f"Error: {e}")

    # 4. Try STK.US.MINOR if it exists
    print("\n=== Test STK.US.MINOR location ===")
    sub3 = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MINOR",
        scanCode="MOST_ACTIVE",
        abovePrice=0.0001,
        belowPrice=0.03,
        numberOfRows=10,
    )
    try:
        results3 = await ib.reqScannerDataAsync(sub3)
        print(f"Results: {len(results3)}")
        for r in results3[:5]:
            c = r.contractDetails.contract
            print(f"  {c.symbol} | exchange={c.exchange} | primaryExchange={c.primaryExchange}")
    except Exception as e:
        print(f"Error: {e}")

    ib.disconnect()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
