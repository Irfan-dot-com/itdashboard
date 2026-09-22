```code
{
      "schema_version": "1.0",
      "edge_id": "edge-box-7",
      "service_provider": "bluip",
      "property_id": "123",
      "property_name": "sheraton",
      "messages": [
          {
              "kind": "edge_health",
              "ts": 1746724100.0,
              "metrics": {
                  "tracked_devices": 5,
                  "unhealthy_devices": 2,
                  "queue_depth": 5,
                  "summary_interval_seconds": 60
              }
          },
          {
              "kind": "periodic",
              "ts": 1746724095.0,
              "device_id": "dev-006",
              "device_name": "wifi_ap_lobby",
              "device_class": "wifi_ap",
              "vendor": "ubiquiti",
              "site": "lobby",
              "health": {
                  "status": "unhealthy",
                  "score": 15,
                  "reasons": ["device_unreachable", "hardware_fault"]
              },
              "metrics": {
                  "event_count": 20,
                  "error_count": 18,
                  "warn_count": 2
              }
          },
          {
              "kind": "transition",
              "ts": 1746724100.0,
              "device_id": "dev-006",
              "device_name": "wifi_ap_lobby",
              "device_class": "wifi_ap",
              "vendor": "ubiquiti",
              "site": "lobby",
              "health": {
                  "status": "unhealthy",
                  "score": 15,
                  "reasons": ["device_unreachable", "hardware_fault"]
              },
              "metrics": {
                  "event_count": 20,
                  "error_count": 18,
                  "warn_count": 2
              },
              "top_events": [
                  {
                      "ts": 1746724090.0,
                      "severity": "error",
                      "category": "connectivity",
                      "message": "Access point UAP-AC-PRO unreachable — ICMP ping timeout after 30s"
                  },
                  {
                      "ts": 1746724085.0,
                      "severity": "error",
                      "category": "hardware",
                      "message": "PoE power budget exceeded on port Gi0/12 — AP lost power"
                  },
                  {
                      "ts": 1746724080.0,
                      "severity": "error",
                      "category": "connectivity",
                      "message": "SSID 'Sheraton-Guest' no longer broadcasting from AP-Lobby-01"
                  },
                  {
                      "ts": 1746724075.0,
                      "severity": "warning",
                      "category": "hardware",
                      "message": "PoE port Gi0/12 power draw spike: 32W (normal: 18W)"
                  }
              ]
          }
      ]
  }

```  