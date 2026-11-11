# Work with media

Start Open Imagine and select Image, Video, Voice, or Music. The available controls follow the selected model.

## Use the studio on a phone

The workspace icon at the top opens Image, Video, Voice, or Music in one header row.
Below 600 pixels of browser width, the bottom navigation switches between Preview, Gallery, and Controls.
At 600 pixels and wider, Preview and Controls appear side by side.
On unfolded screens, Browse opens the gallery while the collapsed gallery keeps more room for the image.
Windows up to 900 pixels keep the workspace icon. Wider windows use the desktop header.
Below 600 pixels, menus and dropdowns fill the screen.
From 600 to 900 pixels, menus and dropdowns open as large centered pickers.
Use Close or tap outside a centered picker to return to the previous control.
Preview keeps metadata behind Details.
More contains Download and Remove on mobile. Zoom opens the larger image viewer.
Pinch or scroll over an image to zoom. Drag a zoomed image to move it.
Double tap or double click restores the whole image and gallery swipes.
Compare sits immediately left of Details. It switches the divider on an edited image.
With Compare on, drag with one finger to move the divider. Use two fingers to move or zoom the image.
With the brush active, one finger paints. Zoom opens a larger view without changing the brush marks.
In short windows, the toolbar scrolls while the image keeps space for drawing.
The Zoom icon opens a larger viewer without a visible title.
Its header centers the zoom level, Fit, and 100%. Close stays at the right.
Close or Escape returns to the preview and keeps its zoom and brush marks.
Foldable cover screens and inner screens keep the current pane and draft when the window changes size.
The image keeps its zoom level when the window changes size.
Preview shortcuts open Controls. Templates, Edit, and reuse actions show the fields they prepare.
Generate opens Preview. Cancel returns to Controls and retains the submitted inputs after the run stops.
If a request fails, Controls shows the retained inputs. Progress and Cancel remain accessible in every pane.

Select a gallery item to open Preview. Swipe left for the next item or right for the previous item.
Swipes follow the same order as the arrow keys. Drawing, waveform selection, and playback controls keep their own gestures.

Look and music style use dropdowns. Select none to clear one choice.
Thin lines divide the plain text rows. A checkmark identifies the selected option.
Taps keep these dropdowns visually neutral.
Music opens Style presets by default. Genre appears inside this section.
Image and Video open Look by default in Generate mode.
Size, resolution, and style controls fill their available width. Options in the same group keep equal widths.
The Music player keeps Play centered. The lyrics switch stays separate from playback controls.

Preview actions use an icon with a short caption underneath in every workspace.
Disabled controls show their reason nearby.
Menu descriptions explain longer actions. Details shows the complete settings for a result.
The studio shows progress, errors, and completion messages immediately.

Image and Video accept HEIC and HEIF references. The studio converts them to PNG without changing the original file.
Images with a long edge above 2,048 pixels offer a resize choice before the reference is added.
Resize is the recommended default. Use original resolution keeps the image dimensions. Cancel keeps the current reference.

## Choose a theme

Open Settings at the top right. In Appearance, choose a theme. This browser keeps your choice.
Darkroom, Leica M, Kodak Instamatic, and Polaroid SX-70 remain available alongside four studio themes:

| Theme | Appearance |
|---|---|
| Blueprint | Cobalt drafting grids, cyan accents, and technical typography. |
| Cel Studio | Animation paper, pencil-blue rules, and vermilion details. |
| Broadcast | Graphite consoles, ivory controls, and segmented progress meters. |
| Risograph | Cream paper, teal and coral ink, and offset print borders. |

Every theme applies to Image, Video, Voice, and Music. Theme surfaces sit behind the previews;
the media itself keeps its original colors. Controls and actions stay in the same places.

## Browse the gallery

Choose **Browse** above any gallery to expand its strip into a grid while keeping one main preview.
Long galleries load previews as you browse instead of decoding every saved file at startup.
Search and keyboard navigation still cover the whole saved gallery; downloads use the original files.
Search prompts, scripts, voice descriptions, model names, or seeds. Filter by model or mode
and choose newest or oldest first. **Group batches** appears when existing operation identities
identify multiple results; open a batch to browse its items and use **All results** to return.

Choose **Select** to mark several results, or select all results matching the current filters.
Download selected saves the complete files; Remove selected asks for confirmation and uses the
same deletion behavior as each gallery's Remove action. Changing filters clears the bulk selection.
The main Voice player's Download action still downloads its chosen time selection.

Visible Video thumbnails silently loop sixteen small frames from the first two seconds (or the whole clip if shorter).
Previews reuse the local video copies and a bounded cache of small image strips, with one
decoder used at a time during capture. They stop when hidden, during Video generation,
or when reduced motion is enabled. Full-quality playback stays in the main player.

Arrow keys browse results. In the grid, Up/Down move a row and Home/End reach the first/last item.
Space plays or pauses the current Video or Voice preview. Escape leaves multiple selection,
then collapses the browser. Typing and ordinary player controls keep their own keyboard behavior.

Each tab remembers its selected item, gallery layout, filters, and scroll position across refreshes
when **Keep in this browser** is enabled. View preferences are separate for each tab and workspace.

## Reuse and edit a result

Select one gallery item, then use its Edit action to prepare the input. Viewing a result alone does not select it for editing.
Use the action menu to reuse its prompt, script, voice, or seed where offered.
Removing an input reference clears that input; deleting gallery media is a separate action.

Image and Video accept HEIC and HEIF photos, including from paste and drag-and-drop.
The importer converts them to PNG copies in memory.
For images above a 2048-pixel long edge, the importer offers a recommended resize before adding the reference.
Resize keeps the image's proportions. Use original resolution keeps its dimensions. Cancel leaves the reference list unchanged.

In Video Edit, choose **Custom** in the effect picker to describe your own change without a LoRA.
Custom uses the input clip as conditioning and requires no effect weights or downloads.
This is experimental: preservation of the source and adherence to the change are not yet validated.
The named effects instead load their specialized LoRAs and use their measured recipes.

For multiple Image edits, add the images as references and choose one result per image.
Add per-reference instructions when each image needs a different change.
Leaving the references as one composition produces one combined image instead.

## Send a reference to another workspace

Use an Image result as a Video keyframe through its action menu.
In Video, capture a source clip’s timeline frame for Image or as a new keyframe.
Each Video image reference sits on a keyframe rail. Drag it along the rail to choose the frame it anchors, or drop a picture on the rail to add it at that frame.
Focus a reference and press the arrow keys to move it one frame, or hold Shift for eight frames.
The imported source clip and generated results have separate galleries.

In Voice, choose a completed clip and drag the waveform’s edge handles or enter Start and End times.
Click the waveform to seek; use Play to hear the selection. Playback speed changes preview speed only.
Use the action menu to send the selection to Video or Clone. These actions prepare inputs without starting a run.
Download or Edit acts on the selection where supported.

## Use prompt aids

Choose Templates for a starting prompt or script. Add a Look where the selected model supports it.
Use Image Rewrite to expand a prompt with the dedicated Image enhancer.
Video Rewrite expands the editable prompt; Generate also applies native enhancement automatically.
Rewrite shows Preparing while the model loads. Cancel appears when the model writes.
If Rewrite cannot start, select it to see the reason immediately.
For AuK Design, pick a voice Template or write a custom description separately from the spoken script.
For Drama-3, put delivery directions in the script and provide a matching transcript when cloning.

## Keep drafts and results

Turn on **Keep in this browser** to retain drafts, references, and saved gallery items across reloads.
A completed operation clears its submitted inputs; newer input drafts are preserved.
Download media to keep it outside browser storage. Audio selection downloads include the selected time range in the filename.
Turn Keep off to clear saved browser media and drafts.
Open tabs retain their existing galleries in memory before saved files are cleared. This can take
time for a large collection; keeping persistence enabled uses less memory while browsing it.

## Cancel a run

Use the shared operation control to cancel. Open tabs follow the same operation, including work started by the API.
Voice shows an illustrative waveform while preparing, fills it according to reported progress,
and holds it while saving. The actual audio waveform appears once the result is ready.
Elapsed time and percentages stay in the shared operation bar; reduced motion disables the animation.
Completed batch items remain available; cancelled inputs are retained for another attempt.
