// src/interface/controllers/SegerToolsController.ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { SegerApiService } from "../../infrastructure/services/SegerApiService.js";

export class SegerToolsController {
  constructor(
    private server: McpServer,
    private segerService: SegerApiService
  ) {
    this.registerTools();
  }

  private registerTools(): void {
    this.registerBaixarFaturasTool();
    this.registerDadosFaturaTool();
  }

  private registerBaixarFaturasTool(): void {
    this.server.tool(
      "baixar-faturas",
      "Baixa as faturas de uma ou mais instalações e retorna os PDFs",
      {
        codInstalacoes: z.array(z.string())
          .describe("Lista de códigos de instalação (ex: ['0160011111','0160022222'])"),
        dataIni: z.string()
          .describe("MÊS-ANO início (ex: 'JAN-2025')"),
        dataFim: z.string()
          .describe("MÊS-ANO fim (ex: 'MAR-2025')"),
      },
      async ({ codInstalacoes, dataIni, dataFim }) => {
        const files = await this.segerService.getFaturas(codInstalacoes, dataIni, dataFim);
        return {
          content: files.map(({ name, content }) => ({
            type: "resource",
            resource: {
              uri: name,                              // nome do arquivo
              blob: content.toString("base64"),       // base64 do PDF
              mimeType: "application/pdf",
            },
          })),
        };
      }
    );
  }

  private registerDadosFaturaTool(): void {
    this.server.tool(
      "dados-fatura",
      "Retorna todos os dados de energia de uma fatura em JSON",
      {
        pdfPath: z.string()
          .describe("Caminho local para o arquivo PDF da fatura no servidor"),
      },
      async ({ pdfPath }) => {
        const dados = await this.segerService.getDadosFatura(pdfPath);
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(dados),  // retorna o objeto JSON como string
            },
          ],
        };
      }
    );
  }
}
