# Ask panel scroll area in real Firefox (159, headless)

The real app at 1366x650 inside a frame of a check page on the same origin. The page opens the Ask tab
(File | Ask tabs, Ask open beside a file), optionally scrolls the list, and prints what scrolls: the
yellow band at the top of each shot is that report, not part of the app. Theme from the app's stored
choice (a seed page on the same origin in a throwaway Firefox profile).

- `before-fix-ask-tab-1366x650-dark.jpg`: before the fades. One scroll area only (`.drawer-body`,
  311px tall, 442px of content); the page does not scroll and the drawer column does not either
  (`overflow: visible`, client height = scroll height). The third card is cut flush at the question
  box with no cue.
- `after-*-list-at-top.jpg`: list at the top: a fade at the bottom edge only.
- `after-*-list-scrolled.jpg`: list scrolled 60px: fades at both edges.

Pixel check just under the header: at the top the banner's own grey shows (light 250, dark 24/24/27);
scrolled, it blends toward the panel ground (light 254, dark 19/19/21).
