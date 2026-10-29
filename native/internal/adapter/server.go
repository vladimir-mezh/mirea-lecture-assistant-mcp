package adapter

import (
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
	"github.com/vladimir-mezh/mirea-lecture-assistant-mcp/native/internal/buildinfo"
)

//go:embed contract.json
var contractJSON []byte

type Caller interface {
	Call(context.Context, string, map[string]any, time.Duration) (map[string]any, error)
}

type contract struct {
	Instructions string `json:"instructions"`
	Tools        []struct {
		Definition mcp.Tool `json:"definition"`
		Method     string   `json:"method"`
		Timeout    int      `json:"timeout"`
	} `json:"tools"`
	Prompts []struct {
		Definition mcp.Prompt `json:"definition"`
		Result     struct {
			Description string `json:"description"`
			Messages    []struct {
				Role    mcp.Role `json:"role"`
				Content struct {
					Type string `json:"type"`
					Text string `json:"text"`
				} `json:"content"`
			} `json:"messages"`
		} `json:"result"`
	} `json:"prompts"`
}

func NewServer(backend Caller) (*mcp.Server, error) {
	var exported contract
	if json.Unmarshal(contractJSON, &exported) != nil || len(exported.Tools) == 0 || exported.Instructions == "" {
		return nil, errors.New("Invalid built-in MCP contract")
	}
	server := mcp.NewServer(&mcp.Implementation{Name: "MIREA Lecture Assistant MCP", Version: buildinfo.Version}, &mcp.ServerOptions{Instructions: exported.Instructions})
	for _, spec := range exported.Tools {
		mcp.AddTool(server, &spec.Definition, func(ctx context.Context, _ *mcp.CallToolRequest, args map[string]any) (*mcp.CallToolResult, any, error) {
			timeout := time.Duration(spec.Timeout) * time.Second
			if spec.Method == "wait_and_check" {
				seconds, ok := args["seconds"].(float64)
				if !ok || seconds < 0 || seconds > 120 || seconds != float64(int(seconds)) {
					return nil, nil, errors.New("seconds must be an integer from 0 to 120")
				}
				timeout = time.Duration(int(seconds)+35) * time.Second
			}
			value, err := backend.Call(ctx, spec.Method, args, timeout)
			return nil, value, err
		})
	}
	for _, spec := range exported.Prompts {
		result := &mcp.GetPromptResult{Description: spec.Result.Description}
		for _, message := range spec.Result.Messages {
			if message.Content.Type != "text" {
				return nil, errors.New("Invalid built-in prompt")
			}
			result.Messages = append(result.Messages, &mcp.PromptMessage{Role: message.Role, Content: &mcp.TextContent{Text: message.Content.Text}})
		}
		server.AddPrompt(&spec.Definition, func(_ context.Context, _ *mcp.GetPromptRequest) (*mcp.GetPromptResult, error) { return result, nil })
	}
	return server, nil
}
