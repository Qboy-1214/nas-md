# Mount API Reference

The Mount API allows browsing, reading, and managing files on server-side directories through the web UI. Mount points are configured via the `MOUNT_DIRS` environment variable (semicolon-separated absolute paths).

## Configuration

### Environment Variable

```
MOUNT_DIRS=/path/to/dir1;/path/to/dir2;/path/to/dir3
```

Each directory becomes a separate mount point, identified by `mount-0`, `mount-1`, etc.

### Docker Compose Example

```yaml
services:
  nas-md:
    volumes:
      - /home/user/notes:/mnt/notes
      - /home/user/docs:/mnt/docs
    environment:
      MOUNT_DIRS: /mnt/notes;/mnt/docs
```

## Data Types

### MountEntry

```json
{
  "id": "mount-0",
  "name": "notes",
  "path": "/mnt/notes"
}
```

### DirEntry

```json
{
  "name": "Projects",
  "path": "/Projects",
  "isDir": true,
  "size": 0,
  "modTime": 1719993600000,
  "children": [
    {
      "name": "README.md",
      "path": "/Projects/README.md",
      "isDir": false,
      "size": 1234,
      "modTime": 1719993600000
    }
  ]
}
```

- `name` — file or directory name
- `path` — relative path from mount root (starts with `/`)
- `isDir` — `true` if directory
- `size` — file size in bytes (0 for directories)
- `modTime` — modification time in milliseconds since epoch
- `children` — child entries (only present for directories in tree responses)

## Endpoints

### List Mount Points

```
GET /api/mounts
```

Returns all configured mount points.

**Response 200:**
```json
[
  { "id": "mount-0", "name": "notes", "path": "/mnt/notes" },
  { "id": "mount-1", "name": "docs", "path": "/mnt/docs" }
]
```

**Response 200 (no mounts):**
```json
[]
```

---

### List Directory Contents

```
GET /api/mounts/{id}/tree?path=/
```

Returns the immediate children of the specified directory.

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `path` | `/` | Relative path from mount root |

**Response 200:**
```json
[
  { "name": "Projects", "path": "/Projects", "isDir": true, "size": 0, "modTime": 1719993600000 },
  { "name": "Welcome.md", "path": "/Welcome.md", "isDir": false, "size": 512, "modTime": 1719993600000 }
]
```

**Response 404:** Mount not found or path does not exist.

---

### Recursive Directory Tree

```
GET /api/mounts/{id}/tree-recursive?path=/
```

Returns the full directory tree up to 10 levels deep.

**Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `path` | `/` | Relative path from mount root |

**Response 200:**
```json
{
  "name": "notes",
  "path": "/",
  "isDir": true,
  "size": 0,
  "modTime": 1719993600000,
  "children": [
    {
      "name": "Projects",
      "path": "/Projects",
      "isDir": true,
      "size": 0,
      "modTime": 1719993600000,
      "children": [
        {
          "name": "README.md",
          "path": "/Projects/README.md",
          "isDir": false,
          "size": 1234,
          "modTime": 1719993600000
        }
      ]
    }
  ]
}
```

**Response 404:** Mount not found.
**Response 500:** Cannot build tree (e.g., permission denied).

---

### Read File

```
GET /api/mounts/{id}/file?path=/file.md
```

Returns the raw file content.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `path` | Yes | Relative path to the file |

**Response 200:** Raw file content with appropriate `Content-Type` header.

Text files (`.md`, `.txt`, `.json`, `.html`, `.css`, `.js`, etc.) are served with `charset=utf-8`.

**Response 400:** Missing path parameter.
**Response 403:** Path escapes mount root.
**Response 404:** File not found.
**Response 500:** Read error.

---

### Write File

```
PUT /api/mounts/{id}/file?path=/file.md
```

Creates or overwrites a file. Parent directories are created automatically.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `path` | Yes | Relative path to the file |

**Request body:** Raw file content (binary).

**Response 200:**
```json
{
  "status": "ok",
  "modTime": 1719993600000,
  "size": 1234
}
```

**Response 400:** Missing path parameter.
**Response 403:** Path escapes mount root.
**Response 404:** Mount not found.

---

### Rename / Move

```
PUT /api/mounts/{id}/rename?oldPath=/old-name.md&newPath=/new-name.md
```

Renames or moves a file or directory within the same mount point.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `oldPath` | Yes | Current relative path |
| `newPath` | Yes | New relative path |

**Response 200:**
```json
{ "status": "ok" }
```

**Response 400:** Missing oldPath or newPath.
**Response 403:** Either path escapes mount root.
**Response 404:** Mount not found.

---

### Create Directory

```
PUT /api/mounts/{id}/mkdir?path=/new-directory
```

Creates a new directory. Parent directories are created automatically.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `path` | Yes | Relative path for the new directory |

**Response 200:**
```json
{ "status": "ok" }
```

**Response 400:** Missing path parameter.
**Response 403:** Path escapes mount root.
**Response 404:** Mount not found.

---

### Delete

```
DELETE /api/mounts/{id}/file?path=/file.md
```

Deletes a file or directory. Directories are deleted recursively (including all contents).

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `path` | Yes | Relative path to the file or directory |

**Response 200:**
```json
{ "status": "ok" }
```

**Response 400:** Missing path parameter.
**Response 403:** Path escapes mount root.
**Response 404:** Mount not found.

---

## Error Responses

All errors return JSON:

```json
{ "error": "Description of the problem" }
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request (missing parameters) |
| 403 | Forbidden (path escapes mount root) |
| 404 | Not found (mount or file doesn't exist) |
| 405 | Method not allowed |
| 500 | Internal server error |

## Security

- **Path traversal protection:** All paths are resolved to real paths and checked to ensure they stay within the mount root. Requests attempting to escape (e.g., `../../etc/passwd`) return 403.
- **Hidden files:** Files and directories starting with `.` are excluded from directory listings.
- **CORS:** All API responses include `Access-Control-Allow-Origin: *`.
- **Gzip compression:** Responses are gzip-compressed when the client supports it.

## Example: JavaScript Client

```javascript
const API = 'http://localhost:8080';

// List mount points
const mounts = await fetch(`${API}/api/mounts`).then(r => r.json());

// Browse a directory
const tree = await fetch(`${API}/api/mounts/mount-0/tree?path=/`).then(r => r.json());

// Read a file
const content = await fetch(`${API}/api/mounts/mount-0/file?path=/notes.md`).then(r => r.text());

// Write a file
await fetch(`${API}/api/mounts/mount-0/file?path=/new.md`, {
  method: 'PUT',
  body: '# Hello\n\nNew note content',
});

// Create a directory
await fetch(`${API}/api/mounts/mount-0/mkdir?path=/Projects`, { method: 'PUT' });

// Rename
await fetch(`${API}/api/mounts/mount-0/rename?oldPath=/old.md&newPath=/new.md`, { method: 'PUT' });

// Delete
await fetch(`${API}/api/mounts/mount-0/file?path=/trash.md`, { method: 'DELETE' });
```
