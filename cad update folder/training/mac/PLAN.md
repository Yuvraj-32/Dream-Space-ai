# Train the DreamSpace door and window detector on a Mac

**Goal:** train a small YOLO model on about 5,300 labelled floor-plan images, so DreamSpace can find single doors, double doors, sliding doors and windows, then send back one zip file. Everything is free and runs on your Mac: no accounts, keys or payments.

**Your time:** about 30 minutes, plus leaving the Mac running for what may be many hours. The trial tells you how long your Mac will take.

**Not tested on a Mac yet:** the code was tested on a Windows PC, without an Apple GPU. If a step misbehaves, stop and send the full error text.

## What you need

| | |
|---|---|
| Mac | Apple Silicon (M1 or newer), macOS 14 or newer |
| Memory | 16 GB or more is best. 8 GB works but is slower |
| Free disk | 8 GB |
| Python | 3.11 or 3.12. If missing, install 3.12 from [python.org](https://www.python.org/downloads/macos/) |
| Power | Plugged in, lid open |

Intel Macs can't do this. Use `colab/dreamspace_train_door_window.ipynb` instead (see "If the trial fails").

## Steps

### 1. Unzip
Unzip this kit somewhere with 8 GB free, and open Terminal in that folder:

```bash
cd ~/Downloads/DreamSpace_mac_training
```

Adjust the path if you unzipped it elsewhere. Don't move the folder once training has started.

### 2. Run the trial (about 10 to 40 minutes)

```bash
bash run_mac.sh trial
```

The first run installs the tools (about 1 GB) and downloads the dataset (454 MB). It then trains for a few minutes on a small part of the data, and compares the Mac's GPU with its CPU.

**Why the trial exists:** people have reported YOLO on Apple's GPU giving wrong results with no error message, such as zero box loss or corrupted box positions. Some of these may already be fixed, but a bad GPU result could waste days, so the kit proves yours is correct first.

It ends with one of these:
- **`TRIAL PASSED`**, plus an estimated time: continue to step 3.
- **`TRIAL FAILED`**: stop, and see "If the trial fails".

### 3. Look at the label check
Open `label_check.jpg` in the kit folder. It should show:

| Box label | Should be on |
|---|---|
| `door_single` (red) | A door with **one** leaf and one curved swing |
| `door_double` (pink) | A door with **two** leaves and two curves |
| `door_sliding` (green) | A thin strip in a wall, often with a door code like `PM...` |
| `window` (blue) | A thin strip in a wall, often with a window code like `C1505` |

The images are Chinese CAD drawings, and that's expected. Some thin strips are hard to tell apart. **If boxes are clearly on the wrong things, stop and tell the project owner.**

### 4. Decide using the estimate
Tell the project owner the estimated hours before starting. It is rough, and training may stop early once the model stops improving. If it's too long for your Mac, Colab may suit better.

### 5. Train

```bash
bash run_mac.sh train
```

Leave it running, plugged in, with the lid open. The Mac stays awake by itself, though it may get warm and fan-noisy. It can do other light work, but heavy apps slow training down.

To check progress, open a second Terminal in the same folder:

```bash
bash run_mac.sh status
```

**If it stops for any reason** (a restart, a closed lid, Ctrl-C), run `bash run_mac.sh train` again. It continues from the last finished epoch.

### 6. Send back the result
When training ends, it measures final scores on the CPU, which takes some minutes, and prints:

```
DONE. Send this one file back: .../dreamspace_results.zip
```

Send that **one zip file** to the project owner. It holds the model, its scores and the training history. Send it through a person-to-person channel, because the model file runs code when opened and should only come from someone trusted.

## If the trial fails
Don't train on the GPU, because the model could look finished and be useless. Send the project owner the last lines of the output, then choose one:

1. **Update macOS** if an update is available, and re-run the trial. GPU faults can be fixed by system updates.
2. **Use Google Colab (recommended fallback):** upload `colab/dreamspace_train_door_window.ipynb` to [colab.research.google.com](https://colab.research.google.com), and follow the steps at the top of the notebook. It uses a free GPU.
3. **Use the CPU:** `bash run_mac.sh trial --device cpu`, then `bash run_mac.sh train --device cpu`. It's correct but very slow, so check the estimate first.

## Other problems

| Problem | What to do |
|---|---|
| Mac becomes very slow, or an out-of-memory error | Run `bash run_mac.sh train --batch 4`. The trial chooses a batch size from the Mac's memory, and this lowers it. |
| Download fails or is very slow | Run the same command again. It picks up where it left off. |
| Warning about `HF_TOKEN` or "unauthenticated requests" | Ignore it. No account is needed; the download just isn't given priority. |
| `Python 3.11 or 3.12 is needed` | Install 3.12 from python.org, reopen Terminal, and run it again. |
| Setup fails partway | Delete the `.venv` folder and run it again. |
| `STOP: expected about ... boxes` | The dataset isn't the version this kit was checked on. Tell the project owner. |
| Want to start again completely | Delete the `work` folder. |

## Rules for this data and code
- **Dataset:** [FloorPlanCAD](https://floorplancad.github.io/) is for **non-commercial use only** (CC BY-NC 4.0). The dataset's authors don't own the drawings' copyright, so don't publish or redistribute the images.
- **YOLO:** Ultralytics YOLO is AGPL-3.0, and the model trained here inherits these limits. It's for development and demos, not a paid product.
- **Don't change the settings:** the image size (800) and the class fix in `prepare_floorplancad.py` are deliberate. This copy of the dataset calls windows "stair" and single doors "double_door". The script corrects that, so please don't "fix" it back.
- **Client drawings:** this kit contains none, and none are needed.

## What's in this kit

| File | What it does |
|---|---|
| `run_mac.sh` | The only command you run |
| `pipeline.py` | The steps: download, convert, trial, train, finish |
| `prepare_floorplancad.py` | Converts the dataset and corrects its class names |
| `train_yolo.py` | Training, with resume |
| `requirements-mac.txt` | Exact versions of the tools |
| `colab/` | The free Colab notebook, as a fallback |
