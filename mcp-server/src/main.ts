import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { SegerApiService } from "./infrastructure/services/SegerApiService.js";
import { SegerToolsController } from "./interface/controllers/SegerToolsController.js";

async function main() {
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
  
  // Configurando e iniciando o servidor
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Seger MCP Server running on stdio");
}

main().catch((error) => {
  console.error("Fatal error in main():", error);
  process.exit(1);
});
