from scipy.optimize import minimize_scalar, minimize
from scipy.optimize import differential_evolution
from scipy.optimize import brute
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from mpl_toolkits.mplot3d import Axes3D
from src.utils.tarifas import calcular_tarifa_verde, calcular_tarifa_azul

def opt_tarifa_verde(dados, tarifas, tarifa_ere):
    resultado = minimize_scalar(
        lambda d: calcular_tarifa_verde(dados, tarifas, tarifa_ere, d)[0],
        bounds=(30, 1000),
        method='bounded'
    )
    demanda_otima = round(resultado.x)
    custo_otimo = resultado.fun
    # resultado = differential_evolution(
    #     func=lambda d: calcular_tarifa_verde(dados, tarifas, d[0]),
    #     bounds=[(30, 1000)],
    #     strategy='best1bin',
    #     popsize=15,
    #     tol=0.01
    # )
    # demanda_otima = round(resultado[0])  # resultado[0] é um ndarray com um valor
    # custo_otimo = resultado[1]
    
    # resultado = brute(
    #     func=lambda d: calcular_tarifa_verde(dados, tarifas, d),
    #     ranges=((30, 1000),),
    #     full_output=True,
    #     finish=None
    # )
    # demanda_otima = int(round(float(resultado[0])))
    # custo_otimo = resultado[1]

    # demanda_otima = resultado[0]
    # custo_otimo = resultado[1]
    
    result = {
        "demanda_otima": demanda_otima,
        "custo_otimo": custo_otimo
    }
    demanda_range = np.linspace(100, 1000, 50)
    custos_verde = [calcular_tarifa_verde(dados, tarifas, tarifa_ere, d)[0] for d in demanda_range]
    plt.figure(figsize=(10, 6))
    plt.plot(demanda_range,custos_verde, label='Custo Total', color='green')
    plt.axvline(demanda_otima, color='red', linestyle='--', label=f'Demanda ótima: {demanda_otima} kW')
    plt.xlabel('Demanda Contratada (kW)')
    plt.ylabel('Custo Anual (R$)')
    plt.title('Tarifa Verde - Custo vs Demanda Contratada')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("/app/src/data/plots/otimizacao_tarifa_verde1.png")
    plt.close()
    return result


def opt_tarifa_azul(dados, tarifas, tarifa_ere):
    resultado = minimize(
        lambda dm: calcular_tarifa_azul(dados, tarifas, tarifa_ere, dm)[0],
        x0=[100, 100],
        bounds=[(30, 1000), (30, 1000)], 
        method='Powell'
    )
    demanda_p_otima = round(resultado.x[0])
    demanda_fp_otima = round(resultado.x[1])
    custo_otimo = resultado.fun

    result = {
        "demanda_p_otima": demanda_p_otima,
        "demanda_fp_otima": demanda_fp_otima,
        "custo_otimo": custo_otimo
    }
    # Geração de grade de valores
    x = np.linspace(30, 1000, 50)  # Demanda ponta
    y = np.linspace(30, 1000, 50)  # Demanda fora de ponta
    X, Y = np.meshgrid(x, y)
    Z = np.array([
        [calcular_tarifa_azul(dados, tarifas, tarifa_ere, [dp, dfp])[0] for dp in x]
        for dfp in y
    ])

    # Gráfico 3D
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection='3d')
    ax.plot_surface(Y, X, Z, cmap='viridis', edgecolor='k')
    ax.set_ylabel('Demanda Ponta (kW)')
    ax.set_xlabel('Demanda Fora Ponta (kW)')
    ax.set_zlabel('Custo Anual (R$)')
    ax.set_title('Tarifa Azul - Custo vs Demandas')
    plt.tight_layout()
    plt.savefig("/app/src/data/plots/otimizacao_tarifa_azul_3d.png")
    plt.close()

    # Gráfico de contorno
    plt.figure(figsize=(10, 6))
    cp = plt.contourf(X, Y, Z, cmap='plasma', levels=30)
    plt.colorbar(cp, label='Custo Anual (R$)')
    plt.xlabel('Demanda Ponta (kW)')
    plt.ylabel('Demanda Fora Ponta (kW)')
    plt.title('Tarifa Azul - Custo Anual (Contorno)')

    # Ponto ótimo
    plt.plot(demanda_p_otima, demanda_fp_otima, 'ro', label='Ótimo')

    # Texto com coordenadas (em branco)
    plt.text(demanda_p_otima + 0.5, demanda_fp_otima + 0.5,
            f'({demanda_p_otima}, {demanda_fp_otima})',
            color='white', fontsize=12, weight='bold')

    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("/app/src/data/plots/otimizacao_tarifa_azul_contorno.png")
    plt.close()
    return result