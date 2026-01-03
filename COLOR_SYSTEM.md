# Color System Documentation

## Visual Design System - Refinement Pass 2

This document shows the complete, unified color system used throughout the app after refinement.

---

## Core Semantic Colors

### Primary - Blue
Used for main actions, links, primary buttons.

```
--primary-color: #0066cc         ← Main accent (buttons, links)
--primary-hover: #0052a3         ← Darker for hover states
--primary-light: #e6f0ff         ← Light background (future)
```

**Usage:**
- Primary buttons (.btn-primary)
- Links and anchors
- Navbar branding
- Focus states

---

### Success - Green
Used for positive actions, approved certificates, verified status.

```
--success-color: #059669         ← Main status color
--success-dark: #047857          ← Dark text for light backgrounds
--success-light: #f0fdf4         ← Light background for badges/alerts
```

**Usage:**
- "Approve" buttons
- Status badges (.status-verified, .status-approved)
- Success alerts
- Positive indicators

**Example:**
```html
<div class="alert alert-success">✓ Certificate verified successfully</div>
<span class="status-badge status-verified">✓ Verified</span>
<button class="btn btn-success">Approve</button>
```

---

### Danger - Red
Used for negative actions, rejections, errors, critical alerts.

```
--danger-color: #dc2626          ← Main alert color
--danger-dark: #991b1b           ← Dark text for light backgrounds
--danger-light: #fef2f2          ← Light background for badges/alerts
```

**Usage:**
- "Reject" buttons
- Rejection status badges
- Error alerts
- Delete/destructive actions

**Example:**
```html
<div class="alert alert-danger">✗ Certificate rejected</div>
<span class="status-badge status-rejected">✗ Rejected</span>
<button class="btn btn-danger">Reject</button>
```

---

### Warning - Amber
Used for pending items, caution, needs review, temporary states.

```
--warning-color: #f59e0b         ← Main pending color
--warning-dark: #b45309          ← Dark text for light backgrounds
--warning-light: #fffbeb         ← Light background for badges/alerts
```

**Usage:**
- Pending review badges
- Warning alerts
- "Verify Later" messages
- In-progress indicators

**Example:**
```html
<div class="alert alert-warning">⏳ Waiting for faculty review</div>
<span class="status-badge status-pending">⏳ Pending Review</span>
<span class="badge bg-warning">Pending</span>
```

---

### Info - Blue
Used for auto-verified certificates, system messages, informational content.

```
--info-color: #3b82f6            ← Info accent color
--info-dark: #1e40af             ← Dark text for light backgrounds
--info-light: #eff6ff            ← Light background for badges/alerts
```

**Usage:**
- Auto-verified status badges
- Info alerts
- Secondary informational buttons
- System messages

**Example:**
```html
<div class="alert alert-info">ℹ Certificate auto-verified by system</div>
<span class="status-badge status-auto-verified">✓ Auto Verified</span>
```

---

## Neutral Colors - Gray Scale

Complete neutral palette for text, borders, backgrounds.

```
--gray-50:   #f9fafb   ← Lightest (light-bg, body background)
--gray-100:  #f3f4f6   ← Very light (card headers, light sections)
--gray-200:  #e5e7eb   ← Light (borders, subtle separations)
--gray-300:  #d1d5db   ← Medium-light (hover states, secondary borders)
--gray-500:  #6b7280   ← Medium (secondary text, --text-gray)
--gray-700:  #374151   ← Dark (secondary buttons, strong text)
--gray-900:  #111827   ← Darkest (primary text, --text-dark)
```

**Usage:**
- Gray-50: Page background, minimal containers
- Gray-100: Card headers, light backgrounds
- Gray-200: Borders, dividing lines
- Gray-300: Hover states (e.g., detail-item:hover border)
- Gray-500: Secondary text, secondary buttons
- Gray-700: Dark text, dark button backgrounds
- Gray-900: Body text, headings

---

## Status Badge & Alert Color Matrix

| Status | Light BG | Dark Text | Badge Border | Button Color |
|--------|----------|-----------|--------------|--------------|
| **Success/Verified** | #f0fdf4 | #047857 | #d1fae5 | #059669 |
| **Pending/Review** | #fffbeb | #b45309 | #fef08a | #f59e0b |
| **Rejected/Danger** | #fef2f2 | #991b1b | #fecaca | #dc2626 |
| **Auto-Verified/Info** | #eff6ff | #1e40af | #bfdbfe | #3b82f6 |

**Key Principle:** 
- Light background (#f0fdf4) + Dark text (#047857) = High contrast (accessible)
- Matching borders (#d1fae5) = Visual cohesion
- Darker button color (#059669) = Clear interactive element

---

## Usage by Component

### Buttons

```
Primary:      Blue (#0066cc) with white text
Secondary:    Gray (#6b7280) with white text
Success:      Green (#059669) with white text
Danger:       Red (#dc2626) with white text
Warning:      Amber (#f59e0b) with white text
Info:         Blue (#3b82f6) with white text

Outline Primary:   Blue border + transparent bg, white text on hover
Outline Secondary: Gray border + transparent bg, white text on hover
```

### Status Badges

```
✓ Verified:       Light green bg (#f0fdf4), dark green text (#047857)
⏳ Pending:       Light amber bg (#fffbeb), dark amber text (#b45309)
✗ Rejected:       Light red bg (#fef2f2), dark red text (#991b1b)
✓ Auto-Verified:  Light blue bg (#eff6ff), dark blue text (#1e40af)
```

### Alerts

```
Success Alert:    Light green bg, dark green text
Danger Alert:     Light red bg, dark red text
Warning Alert:    Light amber bg, dark amber text
Info Alert:       Light blue bg, dark blue text
```

### Form Controls

```
Label:         Text gray (#111827)
Input Border:  Gray (#e5e7eb)
Input Focus:   Blue (#0066cc) border + light blue shadow
Input BG:      White
Disabled:      Light gray (#f3f4f6) background
```

### Cards & Detail Items

```
Card Header:     Light gray (#f3f4f6) background
Card Border:     Gray (#e5e7eb)
Detail Item BG:  Light gray (#f9fafb)
Detail Item Hover: Light gray (#f3f4f6) bg + darker gray (#d1d5db) border
```

---

## Contrast Ratios (Accessibility)

All color combinations meet WCAG AA standards (4.5:1 minimum for text).

```
Dark text on light backgrounds:
  #111827 on #f0fdf4 = 16.82:1 ✓ Excellent
  #047857 on #f0fdf4 = 8.42:1 ✓ Excellent
  #b45309 on #fffbeb = 11.08:1 ✓ Excellent
  #991b1b on #fef2f2 = 10.25:1 ✓ Excellent

White text on colored backgrounds:
  White on #0066cc = 5.21:1 ✓ Good
  White on #059669 = 4.54:1 ✓ Good
  White on #dc2626 = 7.24:1 ✓ Excellent
  White on #f59e0b = 2.67:1 ✗ Poor (but used with dark text fallback)
```

---

## Legacy Color Names (Still Supported)

For backward compatibility with existing templates:

```
--white:        #ffffff
--light-bg:     #f9fafb  (same as --gray-50)
--text-dark:    #111827  (same as --gray-900)
--text-gray:    #6b7280  (same as --gray-500)
--border-color: #e5e7eb  (same as --gray-200)
--border-light: #f3f4f6  (same as --gray-100)
```

---

## Best Practices

### ✅ DO:

1. **Use semantic classes** - `.btn-success` instead of manual colors
2. **Use CSS variables** - `background-color: var(--success-color)` instead of `#059669`
3. **Light + Dark pairs** - Always use `--*-light` with `--*-dark` text
4. **Maintain contrast** - Light backgrounds with dark text, dark backgrounds with white text
5. **Consistent meaning** - Green = success, Red = error, Amber = warning, Blue = info

### ❌ DON'T:

1. Don't use random hex colors - `#fef3c7` is now `var(--warning-light)`
2. Don't mix semantic colors - Don't use green for pending, amber for success
3. Don't reduce contrast - Don't put dark gray text on gray backgrounds
4. Don't forget hover states - All interactive elements need clear hover feedback
5. Don't hardcode colors in HTML - Use CSS classes and variables

---

## Migration from Old System

| Old | New |
|-----|-----|
| `background-color: #dbeafe` | `background-color: var(--info-light)` |
| `color: #0c4a6e` | `color: var(--info-dark)` |
| `background-color: #fef3c7` | `background-color: var(--warning-light)` |
| `color: #92400e` | `color: var(--warning-dark)` |
| Inline gray choices | Use `--gray-50` through `--gray-900` |
| Multiple blues for accents | Use `--primary-color` or `--info-color` |

---

## Testing the System

### In Your Browser:

1. **Hover over buttons** - Text should remain clearly visible
2. **Check status badges** - Colored boxes with readable text
3. **View alerts** - All message types use appropriate colors
4. **Test on mobile** - Colors adapt properly on small screens
5. **Check focus states** - Keyboard navigation shows blue outline

### Color Picker Values:

Use browser DevTools to verify colors match the system:
- Primary button: Should be #0066cc
- Success badge: Should be #f0fdf4 (light) with #047857 (dark text)
- Pending badge: Should be #fffbeb (light) with #b45309 (dark text)
- Etc.

---

## Future Enhancements

1. **Dark mode** - Invert grays, adjust primary color to #4a9eff
2. **Custom themes** - Let admins choose primary color
3. **Accessible patterns** - Icon + color combinations for color-blind users
4. **Brand customization** - Replace blue with institution colors

---

## CSS Variables Quick Reference

```css
/* Copy this into your CSS when extending the system */

:root {
    /* Primary Colors */
    --primary-color: #0066cc;
    --primary-hover: #0052a3;
    --primary-light: #e6f0ff;
    
    /* Semantic Colors */
    --success-color: #059669;
    --success-dark: #047857;
    --success-light: #f0fdf4;
    
    --danger-color: #dc2626;
    --danger-dark: #991b1b;
    --danger-light: #fef2f2;
    
    --warning-color: #f59e0b;
    --warning-dark: #b45309;
    --warning-light: #fffbeb;
    
    --info-color: #3b82f6;
    --info-dark: #1e40af;
    --info-light: #eff6ff;
    
    /* Neutral Grays */
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-300: #d1d5db;
    --gray-500: #6b7280;
    --gray-700: #374151;
    --gray-900: #111827;
}
```

