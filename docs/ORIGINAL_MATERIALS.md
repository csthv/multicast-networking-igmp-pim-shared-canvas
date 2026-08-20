# Original Materials and Preservation Mapping

## Preservation policy

Every file supplied in the uploaded project archive is preserved under `original_submission/` with its original filename and directory grouping. No original report, source file, command note, packet capture, or video was discarded.

The repository additionally creates canonical copies of the Python code under `src/` so GitHub readers can navigate the implementation without opening the submission folder.

## Mapping

| Supplied file | Preserved location | GitHub-facing role |
|---|---|---|
| `Phase_001_Report.pdf` | `original_submission/NE_Phase_001_Sepehr_Rajabi/Phase_001_Report.pdf` | Authoritative Phase 1 report |
| `Phase1_Scapy_Sender.py` | `original_submission/NE_Phase_002_Sepehr_Rajabi/Phase1_Scapy_Sender.py` | Original Phase 1 sender; canonical copy at `src/phase1/sender.py` |
| `Phase1_Scapy_Receiver.py` | `original_submission/NE_Phase_002_Sepehr_Rajabi/Phase1_Scapy_Receiver.py` | Original Phase 1 receiver; canonical copy at `src/phase1/receiver.py` |
| `Commands for both scenarios.txt` | `original_submission/NE_Phase_002_Sepehr_Rajabi/Commands for both scenarios.txt` | Original command notes; normalized examples under `examples/commands/` |
| `NE_Video.mp4` | `original_submission/NE_Phase_002_Sepehr_Rajabi/NE_Video.mp4` | Original demonstration video; retained as a normal Git file (56,326,921 bytes) |
| `Wireshark.pcapng` | `original_submission/NE_Phase_002_Sepehr_Rajabi/Wireshark.pcapng` | Original capture; convenience copy under `evidence/captures/` |
| `Phase_002_Report.pdf` | `original_submission/NE_Phase_002_Sepehr_Rajabi/Phase_002_Report.pdf` | Authoritative Phase 2 report |
| `phase2_mcast_canvas_paint.py` | `original_submission/NE_Phase_002_Sepehr_Rajabi/phase2_mcast_canvas_paint.py` | Original Phase 2 source; canonical copy at `src/phase2/mcast_canvas.py` |

## Naming normalization

The supplied `Commands for both scenarios.txt` invokes `mcast_canvas.py`, while the supplied Phase 2 source filename is `phase2_mcast_canvas_paint.py`. The GitHub-facing source copy is therefore named `src/phase2/mcast_canvas.py` so the command examples and repository structure are consistent. The original filename is still preserved unchanged.

## Integrity

`MANIFEST.sha256` contains SHA-256 values for the preservation files. Verify them with:

```bash
python scripts/verify_repo.py --verify-originals
```

A human-readable table of all preserved hashes is also available in [`ORIGINAL_FILE_MANIFEST.md`](ORIGINAL_FILE_MANIFEST.md).
