# Apple-Inspired Chat Interface - Design Documentation

## Overview
This project is a chat interface built with React and Tailwind CSS, designed to match Apple's design language and aesthetic principles. The UI features clean layouts, refined typography, glass-morphism effects, and smooth interactions characteristic of Apple's design system.

---

## Design Principles

### 1. **Apple Design System**
The interface follows Apple's core design principles:
- **Clarity**: Clean hierarchy with proper spacing and typography
- **Deference**: Content takes center stage with subtle UI elements
- **Depth**: Layers and motion provide hierarchy and vitality

### 2. **Visual Design**
- **Backdrop Blur Effects**: Using `backdrop-blur-xl` for glass-morphism panels
- **Subtle Borders**: `border-black/[0.06]` for extremely subtle dividers
- **Rounded Corners**: Consistent border-radius (8px, 10px, 12px, 16px)
- **Shadow System**: Minimal shadows (`shadow-sm`) for depth
- **Color Palette**:
  - Primary Text: `#1d1d1f` (Apple's near-black)
  - Secondary Text: `#86868b` (Apple's gray)
  - Accent Blue: `#007aff` (iOS system blue)
  - Accent Green: `#34c759` (iOS system green)
  - Background: `#f5f5f7` (Apple's light gray background)
  - White Panels: `bg-white/80` with backdrop blur

---

## Component Architecture

### File Structure
```
/src/app/
├── App.tsx                 # Main application container
└── components/
    ├── TopNav.tsx          # Top navigation with tabs
    ├── ChatSidebar.tsx     # Left sidebar with controls
    ├── ChatMain.tsx        # Main chat area with input
    └── InfoPanel.tsx       # Right information panel
```

### Component Breakdown

#### **1. App.tsx**
Main container managing global state and layout.

**State Management**:
```typescript
const [activeTab, setActiveTab] = useState('Chat');
const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
const [isInfoPanelOpen, setIsInfoPanelOpen] = useState(true);
```

**Layout Structure**:
- Flexbox column layout with full height
- Top navigation bar (fixed height: 56px / h-14)
- Flex-1 content area with three panels
- Background: `bg-[#f5f5f7]` (Apple's signature light gray)

---

#### **2. TopNav.tsx**
Segmented control-style navigation matching Apple's macOS/iOS patterns.

**Key Features**:
- Glass-morphism background: `bg-white/80 backdrop-blur-xl`
- Segmented control with rounded pill design
- Active state with white background and shadow
- Smooth transitions on all interactive elements

**Styling Details**:
```css
Active Tab: bg-white shadow-sm text-[#1d1d1f]
Inactive Tab: text-[#86868b] hover:bg-white/50
```

**Typography**:
- Font size: `text-[13px]` (Apple uses smaller, refined text)
- Font weight: `font-medium` (500 weight)
- Tracking: Inherits from global `-0.01em` letter-spacing

---

#### **3. ChatSidebar.tsx**
Left sidebar with collapsible sections and action buttons.

**Key Features**:
1. **Collapsible State**: Switches between 260px and 64px width
2. **Action Buttons Row**:
   ```tsx
   - Suggest chat (Sparkles icon + text)
   - Edit (Pencil icon)
   - Delete (Trash icon)
   - New Chat (Plus icon in green #34c759)
   ```

3. **Expandable Sections**:
   - File Collection
   - GraphRAG Collection
   - LightRAG Collection
   - Quick Upload
   - Feedback

4. **Search Mode Toggle**:
   - Segmented control for "Search All" vs "Search in File(s)"
   - Active state uses Apple blue (`#007aff`)

**Styling Patterns**:
```css
Panel: bg-white/80 backdrop-blur-xl border-r border-black/[0.06]
Buttons: p-1.5 rounded-lg hover:bg-black/5 transition-colors
Primary Button: bg-[#007aff] hover:bg-[#0051d5]
Icon Color: text-[#86868b] (gray for inactive)
Icon Size: w-4 h-4 (16px)
```

**Transitions**:
- Chevron rotation: `transition-transform` with `rotate-90`
- Hover states: `transition-colors` with duration 200ms
- Background changes: `transition-all`

---

#### **4. ChatMain.tsx**
Central chat area with message display and input controls.

**Key Features**:
1. **Empty State**:
   - Centered gradient icon (blue to purple)
   - Clear messaging about starting conversations
   - Proper vertical and horizontal centering

2. **Message Input Area**:
   ```tsx
   - Rounded container: rounded-2xl
   - Background: bg-[#f5f5f7]
   - Focus ring: focus-within:ring-2 ring-[#007aff]/20
   - Auto-expanding textarea
   - Attachment button (Paperclip)
   - Send button (disabled when empty)
   ```

3. **Settings Bar**:
   - Citation mode dropdown
   - Mindmap toggle checkbox
   - Info panel toggle button

**Input Styling**:
```css
Container: bg-[#f5f5f7] rounded-2xl p-3
Textarea: bg-transparent resize-none text-[15px]
Placeholder: placeholder:text-[#86868b]
Send Button: bg-[#007aff] disabled:opacity-40
```

**Auto-expanding Textarea**:
```typescript
onInput={(e) => {
  const target = e.target as HTMLTextAreaElement;
  target.style.height = 'auto';
  target.style.height = target.scrollHeight + 'px';
}}
```

---

#### **5. InfoPanel.tsx**
Right panel showing conversation metadata.

**Key Features**:
- Glass-morphism panel: `bg-white/80 backdrop-blur-xl`
- Fixed width: `w-[320px]`
- Empty state with icon and message
- Stats cards for Files, Messages, Sources

**Card Styling**:
```css
Background: bg-[#f5f5f7]
Border radius: rounded-xl
Padding: p-4
Text size: text-[12px] for labels, text-[15px] for values
```

---

## Typography System

### Font Family
```css
font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 
             'SF Pro Text', 'Inter', system-ui, sans-serif;
```

### Font Smoothing
```css
-webkit-font-smoothing: antialiased;
-moz-osx-font-smoothing: grayscale;
letter-spacing: -0.01em;
```

### Text Sizes (Apple's Scale)
- `text-[11px]`: Helper text, version numbers
- `text-[12px]`: Labels in cards
- `text-[13px]`: Button text, body text, sidebar items
- `text-[15px]`: Standard body text, input text
- `text-[17px]`: Section headers
- `text-[28px]`: Main headings

---

## Color System

### Primary Colors
```css
--apple-blue: #007aff      /* Primary actions */
--apple-blue-hover: #0051d5 /* Hover state */
--apple-green: #34c759      /* Positive actions */
```

### Neutral Colors
```css
--primary-text: #1d1d1f     /* Main text */
--secondary-text: #86868b   /* Secondary text, icons */
--background: #f5f5f7       /* Page background */
--panel-bg: #ffffff         /* White panels */
--input-bg: #f5f5f7         /* Form inputs */
--border: rgba(0,0,0,0.06)  /* Subtle borders */
```

### Opacity Usage
```css
bg-white/80           /* 80% white for glass effect */
border-black/[0.06]   /* 6% black for subtle borders */
hover:bg-black/5      /* 5% black for hover states */
ring-[#007aff]/20     /* 20% blue for focus rings */
```

---

## Spacing System

### Padding Scale
- `p-1.5`: 6px (small buttons)
- `p-2`: 8px (medium buttons)
- `p-3`: 12px (input containers)
- `p-4`: 16px (panel padding)
- `p-5`: 20px (larger panels)
- `p-6`: 24px (main content areas)

### Gap System
- `gap-1`: 4px (tight groups)
- `gap-2`: 8px (button groups)
- `gap-3`: 12px (form elements)
- `gap-4`: 16px (section spacing)

---

## Interactive Elements

### Button Styles

**Primary Button**:
```tsx
className="px-4 py-2.5 bg-[#007aff] hover:bg-[#0051d5] 
           rounded-lg transition-all shadow-sm text-white"
```

**Secondary Button**:
```tsx
className="px-3 py-1.5 bg-[#f5f5f7] hover:bg-[#e8e8ed] 
           rounded-lg transition-all text-[#1d1d1f]"
```

**Icon Button**:
```tsx
className="p-1.5 rounded-lg hover:bg-black/5 transition-colors"
```

### Transitions
```css
transition-colors     /* Color changes (200ms default) */
transition-all        /* Multiple properties */
transition-transform  /* Rotations, scales */
```

---

## Responsive Considerations

### Panel Widths
- Sidebar: `w-[260px]` (collapsed: `w-16`)
- Info Panel: `w-[320px]`
- Main area: `flex-1` (takes remaining space)

### Max Widths
- Chat input area: `max-w-3xl` (768px)
- Empty state content: `max-w-2xl` (672px)

---

## Key Apple Design Patterns Used

### 1. **Glass-morphism**
```css
bg-white/80 backdrop-blur-xl border border-black/[0.06]
```
Creates the frosted glass effect seen in macOS Big Sur and later.

### 2. **Segmented Controls**
Pill-shaped containers with rounded active states:
```tsx
<div className="bg-[#f5f5f7] rounded-lg">
  <button className="bg-white shadow-sm rounded-md">Active</button>
  <button className="hover:bg-white/50">Inactive</button>
</div>
```

### 3. **Subtle Separators**
Nearly invisible borders that define spaces without harsh lines:
```css
border-b border-black/[0.06]
```

### 4. **Focus States**
Apple uses subtle rings rather than browser defaults:
```css
focus:outline-none focus:ring-2 focus:ring-[#007aff]/20
```

### 5. **Icon Consistency**
All icons from `lucide-react` at consistent sizes:
- Small: `w-3.5 h-3.5` (14px)
- Standard: `w-4 h-4` (16px)
- Medium: `w-5 h-5` (20px)
- Large: `w-8 h-8` (32px)

---

## Implementation Notes

### State Management
Currently uses React `useState` hooks for local component state. For larger applications, consider:
- Context API for global UI state
- Zustand or Redux for complex state management
- React Query for server state

### Accessibility Improvements
Consider adding:
- ARIA labels for icon-only buttons
- Keyboard navigation support
- Focus visible states
- Screen reader announcements

### Performance Optimizations
- Memoize expensive computations with `useMemo`
- Use `React.memo` for pure components
- Implement virtual scrolling for long chat histories
- Lazy load sections with React.lazy

---

## Browser Support

### Required Features
- CSS `backdrop-filter` for blur effects
- CSS custom properties (CSS variables)
- Flexbox layout
- Modern JavaScript (ES6+)

### Tested Browsers
- Chrome 90+
- Safari 14+
- Firefox 88+
- Edge 90+

---

## Development Tips

### Adding New Sections
1. Add to `expandedSections` state in ChatSidebar
2. Create collapsible button with ChevronRight icon
3. Use consistent spacing: `px-4 py-3`
4. Add border separator: `border-b border-black/[0.06]`

### Customizing Colors
All colors are hard-coded for Apple's palette. To customize:
1. Replace `#007aff` with your brand blue
2. Replace `#34c759` with your brand green
3. Adjust gray tones (`#1d1d1f`, `#86868b`)
4. Update background to your preference

### Maintaining Consistency
- Always use the defined text sizes
- Stick to the spacing scale (multiples of 4px)
- Use the established transition classes
- Test in both light backgrounds and white panels

---

## Credits

**Design Inspiration**: Apple Inc. - macOS Big Sur/Ventura, iOS Design System  
**Icons**: Lucide React (https://lucide.dev)  
**Framework**: React 18.3.1  
**Styling**: Tailwind CSS 4.1.12  
**Build Tool**: Vite 6.3.5  

---

## License
This is a design implementation example. Please respect Apple's design trademarks and intellectual property when using these patterns in commercial applications.
