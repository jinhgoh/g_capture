# G Capture

![Platform: Windows 10/11](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4)
![Python: 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Runs offline](https://img.shields.io/badge/runs-offline-success)

A local Windows screen capture and annotation application. Requires Windows 10/11 and Python 3.10 or newer. No network connection, account, telemetry, or cloud upload is used by the app.

## Run

Double-click **G Capture.lnk** to start with the app icon and no console window.
**launch.bat** also starts without keeping a console open (a console may flash briefly).
The shortcut points to this folder and the current Python installation; recreate it if either is moved.

### System tray and startup

Closing the window keeps G Capture running in the system tray with global shortcuts active. Right-click its tray icon (possibly under the hidden-icons arrow) for **Open G Capture**, **Capture region**, **Run at startup**, and **Quit**. Quit fully exits the app; closing the window preserves the current image and annotations in memory.

Uncheck **Run at startup** to stop automatic launches, or check it to launch directly into the tray when you sign in to Windows. You can also press **Win+R**, enter `shell:startup`, and delete **G Capture**. `python app.py --tray` starts in the tray; normal launches show the editor. Restart an already-running instance after installing updates.

To install dependencies or run with a console for troubleshooting:

```powershell
python -m pip install -r requirements.txt
python app.py
```

## Capture

- **Region:** drag a rectangle across the desktop. Supports multiple monitors, including monitors left of the primary display.
- **Freehand:** draw a closed selection; the area outside is transparent in PNG exports.
- **Window / Control:** after clicking, move the pointer over the desired window or native child control. Capture occurs after at least three seconds. Captures visible screen pixels; covered content is not recovered. Browser DOM elements are not native controls.
- **Full screen:** capture the whole virtual desktop.
- **Fixed size:** set the pixel dimensions, click the button, then click to position the rectangle. Dimensions larger than the desktop are clipped.
- **Scrolling:** select only the scrollable content, excluding sticky headers and borders. The app sends wheel events under the pointer and stitches overlapping frames. Keep the pointer in the target and do not interact with other windows. Press **Esc** to finish. Stops at the bottom, after 20 scroll steps, at 30,000 pixels, or if alignment fails. Partial results are preserved. Works best with static documents in apps that scroll under the pointer; not every application or page is supported. The target remains at its final scroll position.
- **Delay:** 0–30 seconds before capture starts or selection appears.

Global shortcuts while the app is running: **Print Screen** region, **Ctrl+Alt+2** full desktop, **Ctrl+Alt+3** window. The app can remain minimized; pressing a shortcut does not launch a closed app.

Click **Shortcuts…** to choose a key and optional Ctrl/Alt/Shift modifiers for each mode, or disable a shortcut. Print Screen and F1–F11 can be used alone; letters and numbers require a modifier. Click **Save** to apply immediately and persist preferences in `settings.json` beside the app. That folder must be writable. Duplicate assignments are rejected. If Windows cannot register a shortcut, the previous preferences are preserved and an error explains the conflict. Unavailable shortcuts at startup are marked in the shortcut bar.

If Print Screen opens the Windows snipping tool, turn off the Print Screen screen-capture option under **Windows Settings > Accessibility > Keyboard**, then save the shortcut again. Other capture apps may also reserve this key. The app does not change Windows settings automatically.

## Edit and export

Pen, translucent highlighter, arrows, rectangles, ellipses, text (including Korean), mosaic, and crop. Select a drawing tool and drag on the image; Text asks for text to place.

Annotations stay editable while the image is open. After adding an annotation, the app switches to **Select** and selects it. Click an existing element to select it (the topmost overlapping element wins), drag inside its selection box to move it, or drag a corner handle to resize it. Text resizing scales its font proportionally. Use **Edit text** or double-click selected text to change its content. Set **Font size**, **Stroke width**, or **Color**, then click **Apply style** to update the selected element. **Delete** removes it. Cropping keeps annotation objects editable.

Undo/redo includes annotation creation, movement, resizing, styling, deletion, and cropping, limited to 20 steps and a pixel budget. Zoom supports fit and 25?200%, with scrollbars for large images. PNG/JPEG/BMP exports and clipboard copies contain the rendered image without selection handles. Exported image files are flattened: reopening them does not restore editable objects. Switching images or closing discards the current annotation objects.

Every completed capture is automatically copied to the Windows clipboard, ready to paste with **Ctrl+V**. Scrolling capture copies the final combined image, including a partial result if scrolling stops early. Canceling a capture leaves the clipboard unchanged. If automatic copying fails, the capture is kept and the status bar explains how to retry.

Save PNG, JPEG, or BMP with **Ctrl+S**; copy the current image after editing with **Ctrl+C**; open an existing image with **Ctrl+O**. PNG retains freehand transparency; JPEG/BMP exports flatten onto white. Clipboard uses standard Windows DIB format without alpha transparency. Recent history stores up to ten original captures in memory only; edited versions must be saved separately. There are no unsaved-changes prompts when capturing, opening images, switching history, or closing. Unsaved edits are not preserved when the current image is replaced or the app closes.

This version does not include OCR, AI background removal/upscaling, automatic face detection, or an installer. Protected video, secure desktops, and some hardware overlays cannot be captured. Scrolling alignment is best effort rather than full compatibility with all applications.

## Verify

```powershell
python -m unittest -v
```

Tests cover exact multi-frame stitching, end-of-scroll detection, mismatch rejection, mosaic boundaries, live desktop grabbing, and editor undo/redo. The desktop test briefly opens a window. Manual testing is still needed across different monitor/DPI layouts and scrollable applications.
