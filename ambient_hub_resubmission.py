import argparse
import csv
import json
import time
from datetime import datetime

WEIGHT_ON = 120.0
WEIGHT_OFF = 80.0
USED_FULL_G = 250.0
VOC_LOW = 150.0
VOC_HIGH = 450.0


def limit(value, low=0.0, high=1.0):
    return max(low, min(value, high))


def make_level(used_g, voc):
    used_part = limit(used_g / USED_FULL_G)
    voc_part = limit((voc - VOC_LOW) / (VOC_HIGH - VOC_LOW))
    return round(((used_part * 0.4) + (voc_part * 0.6)) * 100)


def make_state(level):
    if level < 34:
        return "low"
    if level < 67:
        return "medium"
    return "high"


def update_weight(weight, present, baseline):
    if weight >= WEIGHT_ON:
        if not present:
            present = True
            baseline = weight
        elif baseline is None or weight > baseline:
            baseline = weight
    elif weight <= WEIGHT_OFF:
        present = False
        baseline = None

    used = 0.0
    if present and baseline is not None:
        used = max(0.0, baseline - weight)

    return present, baseline, used


def read_api(url, requests):
    try:
        response = requests.get(url, timeout=2)
        response.raise_for_status()
        return response.json()
    except Exception as error:
        print("ambient error:", error)
        return None


def read_serial_sensor(port, latest):
    while port.in_waiting:
        line = port.readline().decode("utf-8", errors="replace").strip()
        if line.startswith("AW "):
            try:
                latest = json.loads(line[3:])
            except json.JSONDecodeError:
                pass
    return latest


def save_row(writer, output, weight, baseline, used, data, level, state):
    row = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "weight_g": round(weight, 1),
        "baseline_g": round(baseline or 0, 1),
        "solvent_used_g": round(used, 1),
        "voc_index": round(float(data.get("vocIndex", data.get("voc_index", 0)) or 0), 1),
        "co2": data.get("co2", 0),
        "pm2p5": data.get("pm2p5", data.get("pm2_5", 0)),
        "flap_level": level,
        "state": state,
    }
    writer.writerow(row)
    output.flush()
    print(
        row["time"],
        "weight", row["weight_g"],
        "used", row["solvent_used_g"],
        "VOC", row["voc_index"],
        "flap", row["flap_level"],
        row["state"],
    )


def run_demo(output_path, interval):
    samples = [
        (820, 110),
        (810, 130),
        (790, 170),
        (755, 220),
        (710, 290),
        (665, 360),
        (620, 430),
        (700, 280),
        (760, 190),
        (60, 120),
    ]

    fields = [
        "time", "weight_g", "baseline_g", "solvent_used_g",
        "voc_index", "co2", "pm2p5", "flap_level", "state"
    ]

    present = False
    baseline = None

    with open(output_path, "w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()

        for weight, voc in samples:
            present, baseline, used = update_weight(weight, present, baseline)
            level = make_level(used, voc) if present else 0
            state = make_state(level)
            data = {"vocIndex": voc, "co2": 550 + voc, "pm2p5": round(voc / 40, 1)}
            save_row(writer, output, weight, baseline, used, data, level, state)
            time.sleep(interval)


def run_live(args):
    try:
        import serial
    except ImportError:
        raise SystemExit("run: pip install pyserial requests")

    wings = serial.Serial(args.wings, args.wings_baud, timeout=0.1)
    time.sleep(2)

    sensor_serial = None
    requests = None
    latest_sensor = None

    if args.voc.startswith("api:"):
        try:
            import requests as requests_module
        except ImportError:
            raise SystemExit("run: pip install requests")
        requests = requests_module
        sensor_source = args.voc[4:]
    elif args.voc.startswith("serial:"):
        sensor_source = args.voc[7:]
        sensor_serial = serial.Serial(sensor_source, 115200, timeout=0.1)
    else:
        raise SystemExit("--voc must start with api: or serial:")

    fields = [
        "time", "weight_g", "baseline_g", "solvent_used_g",
        "voc_index", "co2", "pm2p5", "flap_level", "state"
    ]

    weight = 0.0
    present = False
    baseline = None
    next_read = time.monotonic()

    with open(args.out, "w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()

        try:
            while True:
                while wings.in_waiting:
                    line = wings.readline().decode("utf-8", errors="replace").strip()
                    if line.startswith("W:"):
                        try:
                            weight = float(line[2:])
                        except ValueError:
                            pass

                now = time.monotonic()
                if now >= next_read:
                    next_read = now + args.interval

                    if sensor_serial:
                        latest_sensor = read_serial_sensor(sensor_serial, latest_sensor)
                        data = latest_sensor
                    else:
                        data = read_api(sensor_source, requests)

                    if data is not None:
                        present, baseline, used = update_weight(weight, present, baseline)
                        voc = float(data.get("vocIndex", data.get("voc_index", 0)) or 0)
                        level = make_level(used, voc) if present else 0
                        state = make_state(level)
                        wings.write(f"F:{level}\n".encode())
                        save_row(writer, output, weight, baseline, used, data, level, state)

                time.sleep(0.02)

        except KeyboardInterrupt:
            wings.write(b"F:0\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--voc")
    parser.add_argument("--wings")
    parser.add_argument("--wings-baud", type=int, default=9600)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--out", default="resubmission_session.csv")
    args = parser.parse_args()

    if args.demo:
        run_demo(args.out, args.interval)
        return

    if not args.voc or not args.wings:
        raise SystemExit("use --demo, or provide --voc and --wings")

    run_live(args)


if __name__ == "__main__":
    main()
