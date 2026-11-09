### The flux2 test

A sample, not every option: the options most likely to behave differently on FLUX.2 klein-base-9B. The runs used "a cat wearing a suit" at 768 x 768, 20 steps, guidance 4, int8, seed 1234, next to the bare prompt. Each template ran with its first fill-in.

| Option | Result on flux2 |
|---|---|
| Medium: Film photo (now Film: Portra 400), Watercolor, 3D render | All three work. 3D render turns the subject into a vinyl toy, which is still a 3D render. |
| Light: Studio | Works: a plain white studio. |
| Light: Night with neon | Works, but dark: the subject is hard to see. |
| Camera: Wide 24mm, Top-down | Both work. |
| Color: Vivid | Works. |
| Color: Black and white (now in the Film row) | The shared sentence names "Kodak Tri-X 400", and flux2 printed that name on a film frame. The flux2 sentence, "Black and white film photograph, strong grain, high contrast.", names no film. On the same seed it kept the grain and the contrast, with no frame and no text. |
| Room for text: Left, Top | Both work. Top is stronger than on qwen21. |
| The 5 generate templates | All work. The poster text came out exact. |
| The 3 edit templates | All work: the recolor, the new background and the added sign. |
| Deadpan absurdity, Banner, Alternate reality, Add an object | Not tested on flux2, so flux2 does not offer them. |

The other 19 Look options were not tested on flux2, so flux2 does not offer them.
