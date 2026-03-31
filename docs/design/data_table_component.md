# DataTable Component — Design Specification

**Related story:** US-6.1
**Stack:** Django templates · HTMX 1.9 · Alpine.js 3 · DaisyUI 5 · Tailwind CSS
**Status:** Design approved, not yet implemented

---

## 1. Overview

A single reusable server-rendered table component that any list view can drop in. All
interactive state (filter builder, column visibility, bulk selection) lives in Alpine.js
and is reflected in the URL via HTMX. The server is the source of truth for data; the
client is the source of truth for ephemeral UI state (filter panel open/closed, selected
rows).

```
┌─────────────────────────────────────────────────────────────────────┐
│  Toolbar: [🔍 Filters ▾] [⊟ Columns ▾]              [bulk actions] │
│  Active filters: [status = COMPLETED ✕] [income ≥ 50000 ✕]        │
├─────────────────────────────────────────────────────────────────────┤
│  ☐  │ Date/Time ↕ │ Input Summary │ Prediction ↕ │ Status ↕ │      │
├─────────────────────────────────────────────────────────────────────┤
│  ☑  │ …           │ …             │ …            │ …        │ [→]  │
│  ☑  │ …           │ …             │ …            │ …        │ [→]  │
│  ☐  │ …           │ …             │ …            │ …        │ [→]  │
├─────────────────────────────────────────────────────────────────────┤
│  ← 1  2  3 →                                                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Template interface

The component is included via a Django template include. The view builds a `table_config`
dict and a `rows` page object, then passes both into the template.

```django
{% include "core/components/data_table/table.html" with
    table_config=table_config
    rows=page_obj
%}
```

### 2.1 `table_config` structure (Python)

```python
table_config = {
    # Required
    "table_id":    "history",              # unique slug; used for localStorage key
    "hx_url":      "/flows/history/",      # HTMX GET target for data refresh
    "hx_target":   "#dt-history-body",     # element to swap (tbody + pagination)

    # Column definitions (ordered list)
    "columns": [
        {
            "key":            "created_at",
            "label":          "Date / Time",
            "sortable":       True,
            "sort_field":     "created_at",   # Django ORM field name
            "filterable":     True,
            "filter_type":    "datetime",     # text|number|datetime|choice
            "filter_choices": [],             # populated when filter_type=choice
            "visible":        True,           # default visibility
            "hideable":       True,           # whether user can hide this col
            "cell_template":  None,           # optional: path to sub-template
        },
        {
            "key":          "input_summary",
            "label":        "Input Summary",
            "sortable":     False,
            "filterable":   False,
            "visible":      True,
            "hideable":     True,
        },
        {
            "key":            "classification",
            "label":          "Prediction",
            "sortable":       True,
            "sort_field":     "parameters__classification",
            "filterable":     True,
            "filter_type":    "choice",
            "filter_choices": ["Approved", "Review", "Declined"],
            "visible":        True,
            "hideable":       True,
        },
        {
            "key":            "status",
            "label":          "Status",
            "sortable":       True,
            "sort_field":     "status",
            "filterable":     True,
            "filter_type":    "choice",
            "filter_choices": ["COMPLETED", "RUNNING", "FAILED", "PENDING"],
            "visible":        True,
            "hideable":       True,
        },
    ],

    # Bulk actions (optional; omit key to disable bulk selection entirely)
    "bulk_actions": [
        {
            "key":       "compare",
            "label":     "Compare Selected",
            "icon":      "chart-bar",        # heroicon name (rendered inline SVG)
            "method":    "GET",              # GET navigates; POST submits form
            "url":       "/flows/comparison/",
            "id_param":  "ids",              # GET: ?ids=a,b,c  POST: form field
            "id_sep":    ",",               # separator for GET ids
            "min_select": 2,
            "max_select": 3,
            "variant":   "btn-outline",
        },
        {
            "key":             "delete",
            "label":           "Delete",
            "icon":            "trash",
            "method":          "POST",
            "url":             "/flows/delete/",
            "id_param":        "ids",
            "min_select":      1,
            "max_select":      None,        # unlimited
            "confirm":         True,
            "confirm_message": "Delete the selected executions? This cannot be undone.",
            "variant":         "btn-error btn-outline",
        },
    ],

    # Active filters — pre-populated from request.GET by the view mixin (see §4)
    "active_filters": [
        # {"field": "status", "op": "eq", "value": "COMPLETED"},
    ],

    # Current sort state — pre-populated by view mixin
    "sort_field": "-created_at",   # leading "-" = descending
}
```

---

## 3. Filter operators

### 3.1 Operator catalogue

| `filter_type` | `op` key       | Label                | Django ORM translation                          |
|---------------|----------------|----------------------|-------------------------------------------------|
| text          | `contains`     | Contains             | `field__icontains`                              |
| text          | `not_contains` | Does not contain     | `~Q(field__icontains=v)`                        |
| text          | `eq`           | Equals               | `field__iexact`                                 |
| text          | `neq`          | Does not equal       | `~Q(field__iexact=v)`                           |
| text          | `starts`       | Starts with          | `field__istartswith`                            |
| text          | `ends`         | Ends with            | `field__iendswith`                              |
| text          | `empty`        | Is empty             | `Q(field__isnull=True) \| Q(field="")`          |
| text          | `not_empty`    | Is not empty         | `~(Q(field__isnull=True) \| Q(field=""))`       |
| number        | `eq`           | =                    | `field__exact`                                  |
| number        | `neq`          | ≠                    | `~Q(field__exact=v)`                            |
| number        | `gt`           | >                    | `field__gt`                                     |
| number        | `gte`          | ≥                    | `field__gte`                                    |
| number        | `lt`           | <                    | `field__lt`                                     |
| number        | `lte`          | ≤                    | `field__lte`                                    |
| number        | `empty`        | Is empty             | `Q(field__isnull=True)`                         |
| number        | `not_empty`    | Is not empty         | `field__isnull=False`                           |
| datetime      | `eq`           | On                   | `field__date` (date part only)                  |
| datetime      | `before`       | Before               | `field__lt`                                     |
| datetime      | `after`        | After                | `field__gt`                                     |
| datetime      | `empty`        | Is empty             | `field__isnull=True`                            |
| datetime      | `not_empty`    | Is not empty         | `field__isnull=False`                           |
| choice        | `eq`           | Is                   | `field__exact`                                  |
| choice        | `neq`          | Is not               | `~Q(field__exact=v)`                            |
| choice        | `empty`        | Is empty             | `Q(field__isnull=True) \| Q(field="")`          |
| choice        | `not_empty`    | Is not empty         | `~(Q(field__isnull=True) \| Q(field=""))`       |

### 3.2 URL encoding

Each active filter contributes three query params, using list notation:

```
?f_field[]=status&f_op[]=eq&f_val[]=COMPLETED
&f_field[]=income&f_op[]=gte&f_val[]=50000
&sort=-created_at
&page=1
```

Django reads them with `request.GET.getlist("f_field[]")` etc.
Multiple filters are combined with AND logic (successive `.filter()` calls on the queryset).

---

## 4. Server-side: `DataTableMixin`

A Django view mixin that handles filter parsing, ORM translation, and sort application.
Views that use the DataTable include this mixin and declare `table_config` as a class
attribute (or build it in `get_context_data`).

```python
# backend/apps/core/mixins.py  (pseudocode — not final implementation)

class DataTableMixin:
    """
    Parses f_field[], f_op[], f_val[], sort from request.GET.
    Applies them to self.get_base_queryset().
    Injects table_config['active_filters'] and table_config['sort_field']
    from request params so the template can re-render filter chips and
    column sort arrows in the correct state.
    """

    # Subclass provides the filter_fields mapping:
    # filter_fields = {
    #   "status": {"type": "choice", "orm_field": "status"},
    #   "income": {"type": "number", "orm_field": "parameters__income"},
    # }
    filter_fields: dict = {}

    def get_filtered_queryset(self, qs):
        fields  = self.request.GET.getlist("f_field[]")
        ops     = self.request.GET.getlist("f_op[]")
        vals    = self.request.GET.getlist("f_val[]")
        for field, op, val in zip(fields, ops, vals):
            if field in self.filter_fields:
                qs = apply_filter(qs, self.filter_fields[field], op, val)
        sort = self.request.GET.get("sort", self.default_sort)
        return qs.order_by(sort), sort

    def build_active_filters(self):
        """Return list of dicts for template chip rendering."""
        ...
```

`apply_filter()` is a module-level function in `core/table_filters.py` that maps
`(field_config, op, val)` → a Q object or `.filter()` call.

---

## 5. Client-side: Alpine.js responsibilities

Alpine.js is loaded once in `base.html` (CDN). Each `<div x-data="dataTable(...)">` root
initialises a component instance.

### 5.1 Component initialisation

```javascript
// Defined in a <script> block in the table template (or a static JS file)
function dataTable(tableId, columnKeys) {
    return {
        // --- column visibility ---
        hiddenCols: JSON.parse(localStorage.getItem(`dt_${tableId}_cols`) || '[]'),
        toggleCol(key) {
            if (this.hiddenCols.includes(key))
                this.hiddenCols = this.hiddenCols.filter(k => k !== key);
            else
                this.hiddenCols.push(key);
            localStorage.setItem(`dt_${tableId}_cols`, JSON.stringify(this.hiddenCols));
        },
        isVisible(key) { return !this.hiddenCols.includes(key); },

        // --- filter builder ---
        filtersOpen: false,
        filterRows: [],           // [{field:'', op:'', value:''}]
        addFilterRow()  { this.filterRows.push({field:'', op:'', value:''}); },
        removeFilter(i) { this.filterRows.splice(i, 1); },
        applyFilters()  {
            // Build URL with f_field[], f_op[], f_val[] params
            // + preserve sort + reset to page 1
            // Then trigger HTMX navigation
            const url = buildFilterUrl(this.filterRows, currentSort());
            htmx.ajax('GET', url, {target: `#dt-${tableId}-body`, pushUrl: url});
            this.filtersOpen = false;
        },
        clearFilters()  {
            this.filterRows = [];
            this.applyFilters();
        },

        // --- bulk selection ---
        selectedIds: new Set(),
        get selectedCount() { return this.selectedIds.size; },
        toggleRow(id)  {
            this.selectedIds.has(id)
                ? this.selectedIds.delete(id)
                : this.selectedIds.add(id);
        },
        toggleAll(ids) {
            ids.every(id => this.selectedIds.has(id))
                ? ids.forEach(id => this.selectedIds.delete(id))
                : ids.forEach(id => this.selectedIds.add(id));
        },
        isSelected(id) { return this.selectedIds.has(id); },
        canAction(min, max) {
            const n = this.selectedCount;
            return n >= min && (max === null || n <= max);
        },
        execBulkAction(method, url, idParam, idSep, confirm_, msg) {
            if (confirm_ && !window.confirm(msg)) return;
            const ids = [...this.selectedIds].join(idSep);
            if (method === 'GET') {
                window.location.href = `${url}?${idParam}=${ids}`;
            } else {
                // Build and submit a hidden form
                submitPostForm(url, {[idParam]: [...this.selectedIds]});
            }
        },
    };
}
```

### 5.2 Column visibility — localStorage key format

```
dt_{table_id}_cols  →  JSON array of hidden column keys
                        e.g.  ["input_summary", "file_size_mb"]
```

---

## 6. Template structure

```
core/components/data_table/
├── table.html          ← outer wrapper, Alpine root, toolbar
├── _filter_panel.html  ← filter builder dropdown (included by table.html)
├── _col_panel.html     ← column visibility dropdown
├── _active_chips.html  ← active-filter chip row
├── _bulk_bar.html      ← bulk actions bar (shown when selectedCount > 0)
├── _thead.html         ← table header row with sort arrows
└── _pagination.html    ← HTMX pagination footer
```

The view's partial response (HTMX target swap) returns just `_tbody_rows.html` +
`_pagination.html`, not the full table. The full `table.html` is only rendered on
initial page load.

---

## 7. Accessibility & UX notes

- Filter panel and column panel are DaisyUI `dropdown` components (keyboard-navigable).
- Active filter chips have a visible ✕ button with `aria-label="Remove filter"`.
- Bulk action buttons include `disabled` attribute and `btn-disabled` class when
  `selectedCount < min_select` or `selectedCount > max_select`.
- Sort icons: `↕` (unsorted), `↑` (asc), `↓` (desc) — toggled via CSS class on `<th>`.
- Column toggles are `<input type="checkbox">` inside the dropdown for native keyboard support.
- Row checkboxes carry `aria-label="Select row"`.
- Empty state (no rows after filtering) renders an inline empty-state panel inside the
  `<tbody>` with a "Clear filters" link.

---

## 8. Dependency additions to `base.html`

Alpine.js is not yet included in the project. One script tag is added to `base.html`:

```html
<!-- Alpine.js (added for DataTable and future interactive components) -->
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
```

`defer` ensures Alpine initialises after the DOM is ready and does not block HTMX.

---

## 9. Integration example — History view

```python
# backend/apps/flows/views.py

class HistoryView(DataTableMixin, LoginRequiredMixin, View):
    default_sort = "-created_at"
    filter_fields = {
        "flow_name": {"type": "text",   "orm_field": "flow_name"},
        "status":    {"type": "choice", "orm_field": "status"},
        "created_at":{"type": "datetime","orm_field": "created_at"},
    }

    def get(self, request):
        qs = FlowExecution.objects.filter(triggered_by=request.user)
        qs, sort = self.get_filtered_queryset(qs)
        page_obj = Paginator(qs, 10).get_page(request.GET.get("page", 1))

        table_config = {
            "table_id":  "history",
            "hx_url":    reverse("flows:history"),
            "hx_target": "#dt-history-body",
            "columns":   HISTORY_COLUMNS,        # module-level constant
            "bulk_actions": HISTORY_BULK_ACTIONS,
            "active_filters": self.build_active_filters(),
            "sort_field": sort,
        }

        if request.headers.get("HX-Request"):
            return render(request, "flows/partials/history_table_body.html",
                          {"rows": page_obj, "table_config": table_config})
        return render(request, "flows/history.html",
                      {"rows": page_obj, "table_config": table_config})
```

---

## 10. Out of scope (v1)

- OR logic between filters (AND only in v1)
- Saved / named filter presets
- Server-side column width persistence
- Virtual scrolling / infinite scroll (standard pagination used)
- Column reordering via drag-and-drop
