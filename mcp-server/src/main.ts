import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { WebSocketServer } from 'ws';
import { SegerApiService } from "./infrastructure/services/SegerApiService.js";
import { SegerToolsController } from "./interface/controllers/SegerToolsController.js";

async function createServer() {
  // Criação da instância do servidor MCP
  const server = new McpServer({
    name: "seger-tools",
    version: "1.0.0",
    capabilities: {
      resources: {},
      tools: {},
    },
  });

  // Inicializando serviços e controladores
  const segerApiService = new SegerApiService();

  // Controlador que registra as ferramentas
  new SegerToolsController(server, segerApiService);
  
  return server;
}

async function main() {
  const args = process.argv.slice(2);
  const mode = args[0] || 'stdio';
  
  if (mode === 'websocket' || mode === 'ws') {
    // Modo WebSocket
    const PORT = parseInt(args[1]) || 8080;
    const wss = new WebSocketServer({ port: PORT });
    
    console.error(`Seger MCP Server starting WebSocket server on port ${PORT}`);
    
    wss.on('connection', async (ws) => {
      console.error('New WebSocket connection established');
      
      try {
        const server = await createServer();
        
        // Create custom transport for WebSocket
        const transport = {
          async start() {
            // Already connected via WebSocket
          },
          async send(message: any) {
            if (ws.readyState === ws.OPEN) {
              ws.send(JSON.stringify(message));
            }
          },
          onmessage: null as ((message: any) => void) | null,
          onerror: null as ((error: Error) => void) | null,
          onclose: null as (() => void) | null,
        };
        
        // Set up WebSocket message handling
        ws.on('message', (data) => {
          try {
            const message = JSON.parse(data.toString());
            if (transport.onmessage) {
              transport.onmessage(message);
            }
          } catch (error) {
            console.error('Error parsing WebSocket message:', error);
          }
        });
        
        ws.on('error', (error) => {
          console.error('WebSocket error:', error);
          if (transport.onerror) {
            transport.onerror(error);
          }
        });
        
        ws.on('close', () => {
          console.error('WebSocket connection closed');
          if (transport.onclose) {
            transport.onclose();
          }
        });
        
        // Connect the MCP server to the custom transport
        await server.connect(transport as any);
        
      } catch (error) {
        console.error('Error setting up MCP server for WebSocket connection:', error);
        ws.close();
      }
    });
    
    wss.on('error', (error) => {
      console.error('WebSocket server error:', error);
    });
    
  } else {
    // Modo padrão (stdio)
    const server = await createServer();
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error("Seger MCP Server running on stdio");
  }
}

main().catch((error) => {
  console.error("Fatal error in main():", error);
  process.exit(1);
});
