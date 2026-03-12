package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

// castHeader represents the first line of an asciinema v2 cast file.
type castHeader struct {
	Version int    `json:"version"`
	Title   string `json:"title"`
}

// VideoEntry is the JSON object returned in the /api/videos response.
type VideoEntry struct {
	Name  string `json:"name"`
	Title string `json:"title"`
	Path  string `json:"path"`
}

func readCastTitle(castPath string) string {
	f, err := os.Open(castPath)
	if err != nil {
		return ""
	}
	defer f.Close()

	// The first line of a v2 cast file is a JSON header.
	buf := make([]byte, 4096)
	n, _ := f.Read(buf)
	firstLine := strings.SplitN(string(buf[:n]), "\n", 2)[0]

	var header castHeader
	if err := json.Unmarshal([]byte(firstLine), &header); err != nil {
		return ""
	}
	return header.Title
}

func apiVideosHandler(w http.ResponseWriter, r *http.Request) {
	videosDir := filepath.Join(".", "videos")

	entries, err := os.ReadDir(videosDir)
	if err != nil {
		// videos dir does not exist yet — return empty list
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte("[]"))
		return
	}

	var videos []VideoEntry
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		if !strings.HasSuffix(strings.ToLower(entry.Name()), ".cast") {
			continue
		}

		castPath := filepath.Join(videosDir, entry.Name())
		nameWithoutExt := strings.TrimSuffix(entry.Name(), filepath.Ext(entry.Name()))

		title := readCastTitle(castPath)
		if title == "" {
			title = nameWithoutExt
		}

		videos = append(videos, VideoEntry{
			Name:  nameWithoutExt,
			Title: title,
			Path:  "videos/" + entry.Name(),
		})
	}

	if videos == nil {
		videos = []VideoEntry{}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(videos)
}

func main() {
	port := flag.Int("port", 10023, "HTTP server port")
	flag.Parse()

	// Serve /api/videos
	http.HandleFunc("/api/videos", apiVideosHandler)

	// Serve all other paths as static files from current directory
	http.Handle("/", http.FileServer(http.Dir(".")))

	addr := fmt.Sprintf(":%d", *port)
	log.Printf("Asciinema Local Player running at http://localhost%s", addr)
	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatalf("Server error: %v", err)
	}
}
