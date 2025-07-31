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
    this.registerStartAnalysisTool();
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

  private registerStartAnalysisTool(): void {
    this.server.tool(
      "seger-tools/start_analysis",
      "Inicia análise energética completa para instalações usando credenciais padrão",
      {
        installations: z.array(z.string())
          .describe("Lista de códigos de instalação (ex: ['0000144112'])"),
        start_date: z.string()
          .describe("Data início no formato MM/YYYY (ex: '05/2024')"),
        end_date: z.string()
          .describe("Data fim no formato MM/YYYY (ex: '04/2025')"),
      },
      async ({ installations, start_date, end_date }) => {
        // Usar credenciais padrão
        const defaultUser = "lohanebpalaoro@gmail.com";
        const defaultPassword = "Lohane@29";
        
        // Converter formato de data MM/YYYY para MMM-YYYY
        const convertDateFormat = (date: string): string => {
          const [month, year] = date.split('/');
          const monthNames = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 
                            'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'];
          const monthIndex = parseInt(month) - 1;
          return `${monthNames[monthIndex]}-${year}`;
        };
        
        try {
          console.error(`[MCP] Iniciando análise para: ${installations.join(', ')}`);
          console.error(`[MCP] Período: ${start_date} até ${end_date}`);
          console.error(`[MCP] Usuário: ${defaultUser}`);
          
          const convertedStartDate = convertDateFormat(start_date);
          const convertedEndDate = convertDateFormat(end_date);
          
          console.error(`[MCP] Datas convertidas: ${convertedStartDate} até ${convertedEndDate}`);
          
          const analysisResult = await this.segerService.analisarFaturas({
            codInstalacao: installations[0], // Por enquanto, usar primeira instalação
            data_inicio: convertedStartDate,
            data_fim: convertedEndDate,
            periodo: convertedEndDate, // Usar data fim como período de referência
            distribuidora: "CPFL", // Distribuidora padrão
            username: defaultUser,
            password: defaultPassword
          });
          
          console.error(`[MCP] Análise concluída com sucesso`);
          
          return {
            content: [
              {
                type: "text",
                text: `Análise da instalação ${installations[0]} concluída com sucesso!\n\n` +
                      `Período analisado: ${start_date} a ${end_date}\n` +
                      `Usuário: ${defaultUser}\n\n` +
                      `Resultados:\n${JSON.stringify(analysisResult, null, 2)}`
              }
            ]
          };
        } catch (error) {
          console.error(`[MCP] Erro na análise:`, error);
          
          return {
            content: [
              {
                type: "text", 
                text: `Erro ao realizar análise da instalação ${installations[0]}:\n` +
                      `${error instanceof Error ? error.message : 'Erro desconhecido'}\n\n` +
                      `Verifique se:\n` +
                      `- A instalação existe: ${installations[0]}\n` +
                      `- O período é válido: ${start_date} a ${end_date}\n` +
                      `- O backend está respondendo corretamente`
              }
            ]
          };
        }
      }
    );
  }
}
