from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import fdb
from flask_bcrypt import Bcrypt
from time import localtime
from fpdf import FPDF


app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave_secreta_ativa_fitness'
bcrypt = Bcrypt(app)


# Conexão com o banco
host = 'localhost'
database = r'C:\Users\Aluno\Downloads\BancodadosATF\TRABALHOATFIT.FDB'
user = 'sysdba'
password = 'sysdba'

con = fdb.connect(
    host=host,
    database=database,
    user=user,
    password=password
)


# Perfis utilizados pelo sistema:
# 1 = administrador, 2 = professor, 3 = aluno.
DIAS_SEMANA = {
    1: 'Segunda-feira', 2: 'Terça-feira', 3: 'Quarta-feira',
    4: 'Quinta-feira', 5: 'Sexta-feira', 6: 'Sábado', 7: 'Domingo'
}

# Nas páginas HTML, os dias são enviados como texto.
DIAS_HTML = {}
for numero, nome in DIAS_SEMANA.items():
    DIAS_HTML[str(numero)] = nome

# Conta apenas as inscrições de alunos em uma aula.
def contar_inscritos(cursor, id_aula):
    cursor.execute("""
        SELECT COUNT(*)
        FROM AGENDAMENTO G
        INNER JOIN USUARIO U ON G.ID_USUARIO = U.ID_USUARIO
        WHERE G.ID_AULA = ? AND U.PERFIL = 3
    """, (id_aula,))

    return cursor.fetchone()[0]


# Busca as aulas do aluno ou as aulas ministradas pelo professor.

def minhas_proximas_aulas(cursor, id_usuario, perfil):

    # Busca as aulas do professor
    if perfil == 2:
        cursor.execute("""
            SELECT M.NOME, M.DESCRICAO, D.DIA_SEMANA,
                   D.HORA_INICIO, D.HORA_FIM
            FROM AULA A
            INNER JOIN MODALIDADE M ON A.ID_MODALIDADE = M.ID_MODALIDADE
            INNER JOIN DIA_SEMANA D ON A.ID_AULA = D.ID_AULA
            WHERE A.ID_USUARIO = ?
            ORDER BY D.DIA_SEMANA, D.HORA_INICIO
        """, (id_usuario,))

    # Busca as aulas agendadas pelo aluno
    else:
        cursor.execute("""
            SELECT M.NOME, M.DESCRICAO, D.DIA_SEMANA,
                   D.HORA_INICIO, D.HORA_FIM
            FROM AGENDAMENTO G
            INNER JOIN AULA A ON G.ID_AULA = A.ID_AULA
            INNER JOIN MODALIDADE M ON A.ID_MODALIDADE = M.ID_MODALIDADE
            INNER JOIN DIA_SEMANA D ON A.ID_AULA = D.ID_AULA
            WHERE G.ID_USUARIO = ?
            ORDER BY D.DIA_SEMANA, D.HORA_INICIO
        """, (id_usuario,))

    registros = cursor.fetchall()
    resultado = []

    # Organiza os dados das aulas
    for nome, descricao, dia, inicio, fim in registros:

        if descricao is None:
            descricao = ''

        aula = {
            'nome': nome,
            'descricao': descricao,
            'dia': DIAS_SEMANA[int(dia)],
            'inicio': str(inicio)[:5],
            'fim': str(fim)[:5]
        }

        resultado.append(aula)

    # Professor vê apenas duas aulas
    if perfil == 2:
        return resultado[:2]

    # Aluno vê todas as aulas agendadas
    return resultado


# Verifica se a hora foi digitada corretamente (exemplo: 08:30).
def horario_valido(horario):
    if len(horario) != 5 or horario[2] != ':':
        return False
    horas = horario[:2]
    minutos = horario[3:]
    if not horas.isdigit() or not minutos.isdigit():
        return False
    return int(horas) <= 23 and int(minutos) <= 59


def realizar_agendamento(cursor, id_usuario, id_aula):
    # Confere se a aula existe e tem vaga.
    cursor.execute('SELECT CAPACIDADE FROM AULA WHERE ID_AULA = ?', (id_aula,))
    aula = cursor.fetchone()
    if not aula:
        return 'Aula não encontrada.', 'erro'

    # Confere se o aluno já está inscrito nessa aula.
    cursor.execute("""
        SELECT ID_AGENDAMENTO FROM AGENDAMENTO
        WHERE ID_USUARIO = ? AND ID_AULA = ?
    """, (id_usuario, id_aula))
    if cursor.fetchone():
        return 'Você já está inscrito nesta aula.', 'erro'

    ocupadas = contar_inscritos(cursor, id_aula)
    if ocupadas >= aula[0]:
        return 'Esta aula está esgotada.', 'erro'

    # Pega os dias e horários da aula que o aluno quer agendar.
    cursor.execute("""
        SELECT DIA_SEMANA, HORA_INICIO, HORA_FIM
        FROM DIA_SEMANA WHERE ID_AULA = ?
    """, (id_aula,))
    horarios_novos = cursor.fetchall()

    # Pega as aulas que o aluno já agendou.
    cursor.execute("""
        SELECT ID_AULA FROM AGENDAMENTO WHERE ID_USUARIO = ?
    """, (id_usuario,))
    aulas_agendadas = cursor.fetchall()

    for inscricao in aulas_agendadas:
        cursor.execute("""
            SELECT DIA_SEMANA, HORA_INICIO, HORA_FIM
            FROM DIA_SEMANA WHERE ID_AULA = ?
        """, (inscricao[0],))
        horarios_marcados = cursor.fetchall()

        for dia_marcado, inicio_marcado, fim_marcado in horarios_marcados:
            for dia_novo, inicio_novo, fim_novo in horarios_novos:
                if dia_marcado == dia_novo:
                    if inicio_marcado < fim_novo and fim_marcado > inicio_novo:
                        return 'Você já tem uma aula agendada nesse dia e horário.', 'erro'

    cursor.execute("""
        INSERT INTO AGENDAMENTO (ID_USUARIO, ID_AULA, DATA_AGENDAMENTO)
        VALUES (?, ?, CURRENT_DATE)
    """, (id_usuario, id_aula))
    con.commit()
    return 'Você está inscrito na aula com sucesso!', 'sucesso'


# Landing page
@app.route('/')
def home():
    return render_template('landingpage.html')


# Função senha forte
def senha_forte(senha):

        if len(senha) < 8:
            return False

        tem_maiuscula = False
        tem_minuscula = False
        tem_numero = False
        tem_especial = False

        for caractere in senha:

            if caractere.isupper():
                tem_maiuscula = True

            if caractere.islower():
                tem_minuscula = True

            if caractere.isdigit():
                tem_numero = True

            if not caractere.isalnum():
                tem_especial = True

        return (
                tem_maiuscula
                and tem_minuscula
                and tem_numero
                and tem_especial
        )


# Cadastrar novo usuário
@app.route('/novo_usuario', methods=['GET', 'POST'])
def novo_usuario():

    # Exibir formulário
    if request.method == 'GET':
        return render_template('novo_usuario.html')

    # Receber dados do formulário
    nome = request.form['nome'].strip()
    email = request.form['email'].strip()
    senha = request.form['senha']
    confirmar_senha = request.form.get('confirmar_senha', '')

    # Verificação campos preenchidos
    if not nome or not email or not senha or not confirmar_senha:

        flash('Preencha todos os campos.', 'erro')
        return redirect(url_for('novo_usuario'))

    # Verificação da força da senha
    if not senha_forte(senha):
        flash(
            'A senha deve ter pelo menos 8 caracteres, '
            'uma letra maiúscula, uma letra minúscula, '
            'um número e um caractere especial.', 'erro'
        )

        return redirect(url_for('novo_usuario'))

    # Verificação se as senhas são iguais
    if senha != confirmar_senha:
        flash('As senhas não são iguais.', 'erro')
        return redirect(url_for('novo_usuario'))

    cursor = con.cursor()

    try:

        # Verificação de e-mail já cadastrado
        cursor.execute(
            """
            SELECT id_usuario FROM USUARIO WHERE UPPER(email) = UPPER(?)
            """,
            (email,)
        )

        usuario_existente = cursor.fetchone()

        if usuario_existente:

            flash('Este e-mail já está cadastrado.', 'erro')
            return redirect(url_for('novo_usuario'))

        # Criptografar a senha
        senha_hash = bcrypt.generate_password_hash(
            senha
        ).decode('utf-8')

        # Cadastrar usuário
        cursor.execute(
            """
            INSERT INTO USUARIO(nome, email, senha, tentativas, ativo, perfil)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (nome, email, senha_hash, 0, 1, 3)
        )

        # Salvar no banco
        con.commit()

        flash('Usuário cadastrado com sucesso!', 'sucesso')

        return redirect(url_for('login'))

    # Tratar erros
    except Exception as e:

        con.rollback()

        flash(f'Erro ao cadastrar usuário: {e}', 'erro')

        return redirect(url_for('novo_usuario'))

    # Fechar o cursor
    finally:
        cursor.close()



# Login
@app.route('/login', methods=['GET', 'POST'])
def login():

    # Se o formulário foi enviado
    if request.method == 'POST':

        # Pegar os dados enviados pelo formulário
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '')

        # Verificar se os campos foram preenchidos
        if not email or not senha:
            flash('Preencha o email e a senha.', 'erro')
            return redirect(url_for('login'))

        cursor = con.cursor()

        try:

            # Buscar usuário pelo e-mail, incluindo o perfil
            cursor.execute(
                """
                SELECT
                    ID_USUARIO,
                    NOME,
                    EMAIL,
                    SENHA,
                    TENTATIVAS,
                    ATIVO,
                    PERFIL
                FROM USUARIO
                WHERE UPPER(EMAIL) = UPPER(?)
                """,
                (email,)
            )

            usuario = cursor.fetchone()

            # Usuário não encontrado
            if not usuario:
                flash('Email ou senha incorretos.', 'erro')
                return redirect(url_for('login'))

            # Organizar os dados do usuário
            (id_usuario, nome, email_banco, senha_hash, tentativas, ativo, perfil) = usuario

            # Caso tentativas esteja NULL no banco
            if tentativas is None:
                tentativas = 0

            # Verificar se o usuário está ativo
            if ativo == 0:
                flash('Usuário inativo ou bloqueado.', 'erro')
                return redirect(url_for('login'))

            # Verificar a senha
            if not senha_hash:
                flash('Email ou senha incorretos.', 'erro')
                return redirect(url_for('login'))

            if bcrypt.check_password_hash(senha_hash, senha):

                # Verificar se o perfil está definido
                if perfil not in (1, 2, 3):
                    flash('Perfil de usuário não definido.', 'erro')
                    return redirect(url_for('login'))

                # Guardar os dados na sessão
                session['id_usuario'] = id_usuario
                session['usuario_nome'] = nome
                session['usuario_email'] = email_banco
                session['perfil'] = perfil

                # Zerar as tentativas
                cursor.execute(
                    """
                    UPDATE USUARIO
                    SET TENTATIVAS = ?
                    WHERE ID_USUARIO = ?
                    """,
                    (0, id_usuario)
                )

                con.commit()

                flash('Login realizado com sucesso!', 'sucesso')

                # Redirecionar conforme o perfil
                if perfil == 1:
                    return redirect(url_for('dashboard_admin'))

                elif perfil == 2:
                    return redirect(url_for('index'))

                elif perfil == 3:
                    return redirect(url_for('index'))

            # Senha incorreta
            tentativas += 1

            # Bloquear após 3 tentativas
            if tentativas >= 3:

                cursor.execute(
                    """
                    UPDATE USUARIO
                    SET TENTATIVAS = ?, ATIVO = ?
                    WHERE ID_USUARIO = ?
                    """,
                    (tentativas, 0, id_usuario)
                )

                con.commit()

                flash('Usuário bloqueado após 3 tentativas.', 'erro')
                return redirect(url_for('login'))

            # Atualizar tentativas
            cursor.execute(
                """
                UPDATE USUARIO
                SET TENTATIVAS = ?
                WHERE ID_USUARIO = ?
                """,
                (tentativas, id_usuario)
            )

            con.commit()

            flash(
                f'Email ou senha incorretos. Tentativa {tentativas} de 3.',
                'erro'
            )

            return redirect(url_for('login'))

        # Erro no banco ou no login
        except Exception as e:
            con.rollback()
            print('Erro no login:', e)
            flash('Ocorreu um erro ao realizar o login.', 'erro')
            return redirect(url_for('login'))

        finally:
            cursor.close()

    return render_template('login.html')



# Início / Dashboard do aluno ou professor
@app.route('/inicio')
def index():
    if 'id_usuario' not in session:
        return redirect(url_for('login'))

    if session.get('perfil') == 1:
        return redirect(url_for('dashboard_admin'))

    perfil = session.get('perfil')
    if perfil not in (2, 3):
        flash('Perfil não definido.', 'erro')
        return redirect(url_for('login'))

    id_usuario = session['id_usuario']
    cursor = con.cursor()
    try:
        if perfil == 2:
            # Cada professor vê somente as aulas atribuídas a ele.
            cursor.execute('SELECT COUNT(*) FROM AULA WHERE ID_USUARIO = ?', (id_usuario,))
            minhas_aulas = cursor.fetchone()[0]
            aulas_disponiveis = 0
        else:
            cursor.execute("""
                SELECT COUNT(*) FROM AGENDAMENTO
                WHERE ID_USUARIO = ?
            """, (id_usuario,))
            minhas_aulas = cursor.fetchone()[0]

            # Conta apenas aulas com vagas em que o aluno não está inscrito.
            cursor.execute('SELECT ID_AULA, CAPACIDADE FROM AULA')
            aulas_cadastradas = cursor.fetchall()

            cursor.execute("""
                SELECT ID_AULA FROM AGENDAMENTO WHERE ID_USUARIO = ?
            """, (id_usuario,))
            minhas_inscricoes = []
            for inscricao in cursor.fetchall():
                minhas_inscricoes.append(inscricao[0])

            aulas_disponiveis = 0
            for id_aula, capacidade in aulas_cadastradas:
                if id_aula not in minhas_inscricoes:
                    if contar_inscritos(cursor, id_aula) < capacidade:
                        aulas_disponiveis += 1

        proximas_aulas = minhas_proximas_aulas(cursor, id_usuario, perfil)
        return render_template(
            'dashboard.html', nome=session['usuario_nome'], perfil=perfil,
            minhas_aulas=minhas_aulas, aulas_disponiveis=aulas_disponiveis,
            proximas_aulas=proximas_aulas
        )
    except Exception as erro:
        con.rollback()
        print('Erro ao carregar dashboard:', erro)
        flash('Não foi possível carregar o dashboard.', 'erro')
        return redirect(url_for('login'))
    finally:
        cursor.close()


# Editar perfil
@app.route('/editar_perfil', methods=['GET', 'POST'])
def editar_perfil():

    # Verifica se o usuário está logado
    if 'id_usuario' not in session:
        return redirect(url_for('login'))

    id_usuario = session['id_usuario']
    perfil = session['perfil']

    if perfil == 1:
        pagina_inicio = 'dashboard_admin'
    else:
        pagina_inicio = 'index'

    # Utiliza a conexão global com o banco
    cursor = con.cursor()

    if request.method == 'POST':

        # Recebe os dados do formulário
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '')
        senha2 = request.form.get('senha2', '')

        # Recebe a foto enviada
        foto = request.files.get('foto')

        try:
            # Verifica se nome e e-mail foram preenchidos
            if not nome or not email:
                flash('Preencha o nome e o e-mail.', 'erro')
                return redirect(url_for('editar_perfil'))

            # Verifica se o e-mail já pertence a outro usuário
            cursor.execute("""
                SELECT id_usuario
                FROM USUARIO
                WHERE UPPER(email) = UPPER(?) AND id_usuario <> ?
            """, (email, id_usuario))

            if cursor.fetchone():
                flash('Este e-mail já está cadastrado.', 'erro')
                return redirect(url_for('editar_perfil'))

            # Verifica se o usuário quer alterar a senha
            if senha or senha2:

                # Exige o preenchimento dos dois campos
                if not senha or not senha2:
                    flash('Preencha os dois campos de senha.', 'erro')
                    return redirect(url_for('editar_perfil'))

                # Primeiro, verifica se a senha é forte
                if not senha_forte(senha):
                    flash(
                        'A senha deve ter pelo menos 8 caracteres, '
                        'uma letra maiúscula, uma letra minúscula, '
                        'um número e um caractere especial.',
                        'erro'
                    )
                    return redirect(url_for('editar_perfil'))

                # Depois, verifica se as senhas são iguais
                if senha != senha2:
                    flash('As senhas não são iguais.', 'erro')
                    return redirect(url_for('editar_perfil'))

                # Busca a senha atual e as duas senhas anteriores
                cursor.execute("""
                    SELECT senha, senha1, senha2
                    FROM USUARIO
                    WHERE id_usuario = ?
                """, (id_usuario,))

                resultado = cursor.fetchone()

                senha_atual = resultado[0]
                senha_anterior1 = resultado[1]
                senha_anterior2 = resultado[2]

                # Compara a nova senha com a senha atual
                if senha_atual and bcrypt.check_password_hash(
                    senha_atual, senha
                ):
                    flash(
                        'Você não pode reutilizar a senha atual.',
                        'erro'
                    )
                    return redirect(url_for('editar_perfil'))

                # Compara com a primeira senha anterior
                if senha_anterior1 and bcrypt.check_password_hash(
                    senha_anterior1, senha
                ):
                    flash(
                        'Você já utilizou essa senha anteriormente.',
                        'erro'
                    )
                    return redirect(url_for('editar_perfil'))

                # Compara com a segunda senha anterior
                if senha_anterior2 and bcrypt.check_password_hash(
                    senha_anterior2, senha
                ):
                    flash(
                        'Você já utilizou essa senha anteriormente.',
                        'erro'
                    )
                    return redirect(url_for('editar_perfil'))

                # Criptografa a nova senha
                nova_senha_hash = bcrypt.generate_password_hash(
                    senha
                ).decode('utf-8')

                # Atualiza o histórico das senhas
                cursor.execute("""
                    UPDATE USUARIO
                    SET senha2 = senha1,
                        senha1 = senha,
                        senha = ?
                    WHERE id_usuario = ?
                """, (nova_senha_hash, id_usuario))

            # Atualiza o nome e o e-mail
            cursor.execute("""
                UPDATE USUARIO
                SET nome = ?, email = ?
                WHERE id_usuario = ?
            """, (nome, email, id_usuario))

            # Salva a foto na pasta static/img/perfis.
            if foto and foto.filename:
                nome_original = foto.filename.lower()

                if nome_original.endswith('.png'):
                    extensao = '.png'
                elif nome_original.endswith('.jpg') or nome_original.endswith('.jpeg'):
                    extensao = '.jpg'
                else:
                    con.rollback()
                    flash('Escolha uma foto JPG ou PNG.', 'erro')
                    return redirect(url_for('editar_perfil'))

                # A pasta static/img/perfis já existe no projeto.
                nome_foto = 'perfil_' + str(id_usuario) + extensao
                foto.save(app.static_folder + '/img/perfis/' + nome_foto)

                cursor.execute("""
                    UPDATE USUARIO SET FOTO_PERFIL = ? WHERE ID_USUARIO = ?
                """, ('img/perfis/' + nome_foto, id_usuario))

            # Salva as alterações no banco
            con.commit()

            # Atualiza os dados da sessão
            session['usuario_nome'] = nome
            session['usuario_email'] = email

            flash('Perfil atualizado com sucesso!', 'sucesso')
            return redirect(url_for('editar_perfil'))

        except Exception as erro:
            con.rollback()
            print('Erro ao editar perfil:', erro)

            flash(
                'Ocorreu um erro ao atualizar o perfil.',
                'erro'
            )

            return redirect(url_for('editar_perfil'))

        finally:
            # Fecha somente o cursor, não a conexão global
            cursor.close()

    # Busca os dados atuais do usuário
    try:
        cursor.execute("""
            SELECT nome, email, FOTO_PERFIL
            FROM USUARIO
            WHERE id_usuario = ?
        """, (id_usuario,))

        usuario = cursor.fetchone()

    finally:
        cursor.close()

    # Verifica se encontrou o usuário
    if not usuario:
        flash('Usuário não encontrado.', 'erro')
        return redirect(url_for('login'))

    # Abre a página de perfil
    return render_template(
        'editar_perfil.html',
        nome=usuario[0],
        email=usuario[1],
        foto_perfil=usuario[2],
        pagina_inicio=pagina_inicio
    )
# Logout
@app.route('/logout')
def logout():

    # Apagar os dados da sessão
    session.clear()

    flash('Você saiu da sua conta, com sucesso!', 'sucesso')

    return redirect(url_for('login'))


@app.route('/cadastrar_modalidade', methods=['GET', 'POST'])
def cadastrar_modalidade():

    # Verifica se o usuário está logado
    if 'id_usuario' not in session:
        flash('Faça login para acessar esta página.', 'erro')
        return redirect(url_for('login'))

    cursor = con.cursor()

    try:
        # Verifica se o usuário é administrador
        cursor.execute("""
            SELECT PERFIL
            FROM USUARIO
            WHERE ID_USUARIO = ?
        """, (session['id_usuario'],))

        usuario = cursor.fetchone()

        # PERFIL = 1 significa administrador
        if not usuario or usuario[0] != 1:
            flash('Acesso permitido somente ao administrador.', 'erro')
            return redirect(url_for('index'))

        # Se o formulário for enviado
        if request.method == 'POST':

            # Recebe os dados do formulário
            nome = request.form.get('nome', '').strip()
            descricao = request.form.get('descricao', '').strip()

            # Verifica se o nome foi preenchido
            if not nome:
                flash('Informe o nome da modalidade.', 'erro')
                return redirect(url_for('cadastrar_modalidade'))

            # Verifica se a modalidade já está cadastrada
            cursor.execute("""
                SELECT ID_MODALIDADE
                FROM MODALIDADE
                WHERE UPPER(NOME) = UPPER(?)
            """, (nome,))

            modalidade_existente = cursor.fetchone()

            if modalidade_existente:
                flash('Esta modalidade já está cadastrada.', 'erro')
                return redirect(url_for('cadastrar_modalidade'))

            # Insere a modalidade no banco de dados
            cursor.execute("""
                INSERT INTO MODALIDADE (NOME, DESCRICAO, ATIVO)
                VALUES (?, ?, ?)
            """, (nome, descricao if descricao else None, 1))

            # Confirma a gravação no banco
            con.commit()

            flash('Modalidade cadastrada com sucesso!', 'sucesso')
            return redirect(url_for('cadastrar_modalidade'))

        # Abre a página quando acessada pelo navegador
        return render_template('cadastrar_modalidade.html')

    except Exception as erro:
        # Desfaz alterações se ocorrer algum erro
        con.rollback()

        print('Erro ao cadastrar modalidade:', erro)

        flash('Não foi possível cadastrar a modalidade.', 'erro')
        return redirect(url_for('cadastrar_modalidade'))

    finally:
        # Fecha o cursor ao terminar
        cursor.close()




# Dashboard administrativo
@app.route('/dashboard_admin')
def dashboard_admin():
    if 'id_usuario' not in session:
        return redirect(url_for('login'))

    if session.get('perfil') != 1:
        flash('Acesso permitido somente ao administrador.', 'erro')
        return redirect(url_for('index'))

    cursor = con.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM USUARIO WHERE PERFIL = 3')
        total_alunos = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM AULA')
        total_aulas = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM USUARIO WHERE PERFIL = 2')
        total_professores = cursor.fetchone()[0]

        return render_template('dashboard_admin.html',
                               total_alunos=total_alunos,
                               total_aulas=total_aulas,
                               total_professores=total_professores)
    except Exception as erro:
        con.rollback()
        print('Erro no dashboard do administrador:', erro)
        flash('Não foi possível carregar o dashboard.', 'erro')
        return redirect(url_for('login'))
    finally:
        cursor.close()


@app.route('/listar_modalidades')
def listar_modalidades():

    # Verifica se o usuário está logado
    if 'id_usuario' not in session:
        flash('Faça login para acessar esta página.', 'erro')
        return redirect(url_for('login'))

    cursor = con.cursor()

    try:
        # Verifica se o usuário é administrador
        cursor.execute("""
            SELECT PERFIL
            FROM USUARIO
            WHERE ID_USUARIO = ?
        """, (session['id_usuario'],))

        usuario = cursor.fetchone()

        if not usuario or usuario[0] != 1:
            flash('Acesso permitido somente ao administrador.', 'erro')
            return redirect(url_for('index'))

        # Busca todas as modalidades cadastradas
        cursor.execute("""
            SELECT ID_MODALIDADE, NOME, DESCRICAO, ATIVO
            FROM MODALIDADE
            ORDER BY NOME
        """)

        modalidades = cursor.fetchall()

        # Envia os dados para a página HTML
        return render_template(
            'listar_modalidades.html',
            modalidades=modalidades
        )

    except Exception as erro:
        con.rollback()
        print('Erro ao listar modalidades:', erro)

        flash('Não foi possível carregar as modalidades.', 'erro')
        return redirect(url_for('dashboard_admin'))

    finally:
        cursor.close()



@app.route('/editar_modalidade/<int:id_modalidade>', methods=['GET', 'POST'])
def editar_modalidade(id_modalidade):

    # Verifica se o usuário está logado
    if 'id_usuario' not in session:
        flash('Faça login para acessar esta página.', 'erro')
        return redirect(url_for('login'))

    cursor = con.cursor()

    try:
        # Verifica se o usuário é administrador
        cursor.execute("""
            SELECT PERFIL
            FROM USUARIO
            WHERE ID_USUARIO = ?
        """, (session['id_usuario'],))

        usuario = cursor.fetchone()

        if not usuario or usuario[0] != 1:
            flash('Acesso permitido somente ao administrador.', 'erro')
            return redirect(url_for('index'))

        # Busca a modalidade pelo ID
        cursor.execute("""
            SELECT ID_MODALIDADE, NOME, DESCRICAO, ATIVO
            FROM MODALIDADE
            WHERE ID_MODALIDADE = ?
        """, (id_modalidade,))

        modalidade = cursor.fetchone()

        if not modalidade:
            flash('Modalidade não encontrada.', 'erro')
            return redirect(url_for('listar_modalidades'))

        # Se o formulário for enviado
        if request.method == 'POST':

            nome = request.form.get('nome', '').strip()
            descricao = request.form.get('descricao', '').strip()
            ativo = request.form.get('ativo', str(modalidade[3]))

            # Verifica se o nome foi preenchido
            if not nome:
                flash('Informe o nome da modalidade.', 'erro')

                return render_template(
                    'editar_modalidade.html',
                    modalidade=modalidade
                )

            # Verifica se já existe outra modalidade com o mesmo nome
            cursor.execute("""
                SELECT ID_MODALIDADE
                FROM MODALIDADE
                WHERE UPPER(NOME) = UPPER(?)
                  AND ID_MODALIDADE <> ?
            """, (nome, id_modalidade))

            duplicada = cursor.fetchone()

            if duplicada:
                flash('Já existe uma modalidade com esse nome.', 'erro')

                return render_template(
                    'editar_modalidade.html',
                    modalidade=modalidade
                )

            # Atualiza os dados da modalidade
            cursor.execute("""
                UPDATE MODALIDADE
                SET NOME = ?, DESCRICAO = ?, ATIVO = ?
                WHERE ID_MODALIDADE = ?
            """, (nome, descricao or None, int(ativo) if ativo in ('0', '1') else 1, id_modalidade))

            con.commit()

            flash('Modalidade atualizada com sucesso!', 'sucesso')
            return redirect(url_for('listar_modalidades'))

        # Abre o formulário preenchido
        return render_template(
            'editar_modalidade.html',
            modalidade=modalidade
        )

    except Exception as erro:
        con.rollback()
        print('Erro ao editar modalidade:', erro)

        flash('Não foi possível editar a modalidade.', 'erro')
        return redirect(url_for('listar_modalidades'))

    finally:
        cursor.close()



@app.route('/excluir_modalidade/<int:id_modalidade>', methods=['POST'])
def excluir_modalidade(id_modalidade):

    # Verifica se o usuário está logado
    if 'id_usuario' not in session:
        flash('Faça login para acessar esta página.', 'erro')
        return redirect(url_for('login'))

    cursor = con.cursor()

    try:
        # Verifica se o usuário é administrador
        cursor.execute("""
            SELECT PERFIL
            FROM USUARIO
            WHERE ID_USUARIO = ?
        """, (session['id_usuario'],))

        usuario = cursor.fetchone()

        if not usuario or usuario[0] != 1:
            flash('Acesso permitido somente ao administrador.', 'erro')
            return redirect(url_for('index'))

        # Verifica se a modalidade existe
        cursor.execute("""
            SELECT ID_MODALIDADE
            FROM MODALIDADE
            WHERE ID_MODALIDADE = ?
        """, (id_modalidade,))

        modalidade = cursor.fetchone()

        if not modalidade:
            flash('Modalidade não encontrada.', 'erro')
            return redirect(url_for('listar_modalidades'))

        # Verifica se existem aulas vinculadas à modalidade
        cursor.execute("""
            SELECT FIRST 1 ID_AULA
            FROM AULA
            WHERE ID_MODALIDADE = ?
        """, (id_modalidade,))

        aula = cursor.fetchone()

        if aula:
            flash(
                'Não é possível excluir esta modalidade, pois existem aulas vinculadas a ela.',
                'erro'
            )
            return redirect(url_for('listar_modalidades'))

        # Exclui a modalidade
        cursor.execute("""
            DELETE FROM MODALIDADE
            WHERE ID_MODALIDADE = ?
        """, (id_modalidade,))

        con.commit()

        flash('Modalidade excluída com sucesso!', 'sucesso')
        return redirect(url_for('listar_modalidades'))

    except Exception as erro:
        con.rollback()
        print('Erro ao excluir modalidade:', erro)

        flash('Não foi possível excluir a modalidade.', 'erro')
        return redirect(url_for('listar_modalidades'))

    finally:
        cursor.close()

#Cadastrar Aula
@app.route('/cadastrar_aula', methods=['GET', 'POST'])
def cadastrar_aula():

    # Verifica se o usuário está logado
    if 'id_usuario' not in session:
        flash('Faça login para acessar esta página.', 'erro')
        return redirect(url_for('login'))

    cursor = con.cursor()

    try:
        # Verifica se o usuário é administrador
        cursor.execute("""
            SELECT PERFIL
            FROM USUARIO
            WHERE ID_USUARIO = ?
        """, (session['id_usuario'],))

        usuario = cursor.fetchone()

        if not usuario or usuario[0] != 1:
            flash('Acesso permitido somente ao administrador.', 'erro')
            return redirect(url_for('index'))

        # Busca as modalidades ativas
        cursor.execute("""
            SELECT ID_MODALIDADE, NOME
            FROM MODALIDADE
            WHERE ATIVO = 1
            ORDER BY NOME
        """)

        modalidades = cursor.fetchall()

        # Busca os professores ativos
        cursor.execute("""
            SELECT ID_USUARIO, NOME
            FROM USUARIO
            WHERE PERFIL = 2
              AND ATIVO = 1
            ORDER BY NOME
        """)

        professores = cursor.fetchall()

        # Verifica se o formulário foi enviado
        if request.method == 'POST':

            modalidade = request.form['modalidade'].strip()
            professor = request.form['professor'].strip()
            dias_selecionados = request.form.getlist('dias')
            hora_inicio = request.form['hora_inicio'].strip()
            hora_fim = request.form['hora_fim'].strip()
            capacidade_texto = request.form['capacidade'].strip()

            # Verifica os campos obrigatórios
            if (
                not modalidade
                or not professor
                or not dias_selecionados
                or not hora_inicio
                or not hora_fim
                or not capacidade_texto
            ):
                flash('Preencha todos os campos obrigatórios.','erro')

                return render_template(
                    'cadastrar_aula.html',
                    modalidades=modalidades,
                    professores=professores
                )

            # Converte os valores numéricos
            try:
                modalidade_id = int(modalidade)
                professor_id = int(professor)
                capacidade = int(capacidade_texto)

                dias = []
                for dia in dias_selecionados:
                    dias.append(int(dia))

            except ValueError:
                flash('Os dados informados são inválidos.','erro')

                return render_template(
                    'cadastrar_aula.html',
                    modalidades=modalidades,
                    professores=professores
                )

            # Valida a capacidade
            if capacidade < 1 or capacidade > 18:
                flash('A capacidade deve estar entre 1 e 18 alunos.','erro')

                return render_template(
                    'cadastrar_aula.html',
                    modalidades=modalidades,
                    professores=professores
                )

            # Verifica se algum dia é inválido ou foi escolhido duas vezes.
            dias_invalidos = False
            for dia in dias:
                if dia < 1 or dia > 7 or dias.count(dia) > 1:
                    dias_invalidos = True

            if dias_invalidos:
                flash('Selecione dias da semana válidos.','erro')

                return render_template(
                    'cadastrar_aula.html',
                    modalidades=modalidades,
                    professores=professores
                )

            # Valida o formato dos horários
            if not horario_valido(hora_inicio) or not horario_valido(hora_fim):
                flash('Informe horários válidos.', 'erro')

                return render_template(
                    'cadastrar_aula.html',
                    modalidades=modalidades,
                    professores=professores
                )

            # Verifica se o horário final é posterior ao inicial
            if hora_fim <= hora_inicio:
                flash('O horário de término deve ser posterior ao início.','erro')

                return render_template(
                    'cadastrar_aula.html',
                    modalidades=modalidades,
                    professores=professores
                )

            # Confirma que a modalidade existe e está ativa
            cursor.execute("""
                SELECT ID_MODALIDADE
                FROM MODALIDADE
                WHERE ID_MODALIDADE = ?
                  AND ATIVO = 1
            """, (modalidade_id,))

            if not cursor.fetchone():
                flash('Selecione uma modalidade ativa.','erro')

                return render_template(
                    'cadastrar_aula.html',
                    modalidades=modalidades,
                    professores=professores
                )

            # Confirma que o professor existe e está ativo
            cursor.execute("""
                SELECT ID_USUARIO
                FROM USUARIO
                WHERE ID_USUARIO = ?
                  AND PERFIL = 2
                  AND ATIVO = 1
            """, (professor_id,))

            if not cursor.fetchone():
                flash('Selecione um professor ativo válido.','erro')

                return render_template(
                    'cadastrar_aula.html',
                    modalidades=modalidades,
                    professores=professores
                )

            # Verifica conflitos de horário do professor
            for dia in dias:
                cursor.execute("""
                               SELECT FIRST 1 A.ID_AULA
                               FROM AULA A
                                   INNER JOIN DIA_SEMANA D
                               ON A.ID_AULA = D.ID_AULA
                               WHERE A.ID_USUARIO = ?
                                 AND D.DIA_SEMANA = ?
                                 AND D.HORA_INICIO
                                   < ?
                                 AND D.HORA_FIM
                                   > ?
                               """, (
                                   professor_id,
                                   dia,
                                   hora_fim,
                                   hora_inicio
                               ))

                aula_conflito = cursor.fetchone()

                if aula_conflito:
                    flash(
                        'Conflito de horário! Esse professor já possui '
                        'uma aula nesse dia e horário.',
                        'erro'
                    )

                    return render_template(
                        'cadastrar_aula.html',
                        modalidades=modalidades,
                        professores=professores
                    )

            # Cadastra a aula
            cursor.execute("""
                INSERT INTO AULA
                    (CAPACIDADE, ID_MODALIDADE, ID_USUARIO)
                VALUES (?, ?, ?)
                RETURNING ID_AULA
            """, (
                capacidade,
                modalidade_id,
                professor_id
            ))

            id_aula = cursor.fetchone()[0]

            # Cadastra os dias e horários selecionados
            for dia in dias:
                cursor.execute("""
                    INSERT INTO DIA_SEMANA
                        (ID_AULA, DIA_SEMANA, HORA_INICIO, HORA_FIM)
                    VALUES (?, ?, ?, ?)
                """, (
                    id_aula,
                    dia,
                    hora_inicio,
                    hora_fim
                ))

            # Salva os registros no banco de dados
            con.commit()

            flash( 'Aula cadastrada com sucesso!','sucesso')

            return redirect(url_for('cadastrar_aula'))

        # Exibe o formulário
        return render_template(
            'cadastrar_aula.html',
            modalidades=modalidades,
            professores=professores
        )

    except Exception as erro:
        con.rollback()

        print('Erro ao cadastrar aula:', erro)

        flash('Não foi possível cadastrar a aula.','erro')

        return redirect(url_for('dashboard_admin'))

    finally:
        cursor.close()

# Grade de aulas: cada perfil é direcionado à sua própria visão.
@app.route('/grade_de_aulas')
def grade_de_aulas():
    if 'id_usuario' not in session:
        return redirect(url_for('login'))

    perfil = session.get('perfil')
    if perfil == 2:
        return redirect(url_for('grade_aulas_professor'))
    if perfil == 3:
        return redirect(url_for('grade_aulas_aluno'))
    if perfil != 1:
        return redirect(url_for('login'))

    cursor = con.cursor()
    try:
        cursor.execute("""
            SELECT A.ID_AULA, M.NOME, U.NOME, A.CAPACIDADE,
                   D.DIA_SEMANA, D.HORA_INICIO, D.HORA_FIM
            FROM AULA A
            INNER JOIN MODALIDADE M ON A.ID_MODALIDADE = M.ID_MODALIDADE
            INNER JOIN USUARIO U ON A.ID_USUARIO = U.ID_USUARIO
            INNER JOIN DIA_SEMANA D ON A.ID_AULA = D.ID_AULA
            ORDER BY D.DIA_SEMANA, D.HORA_INICIO, M.NOME
        """)
        registros = cursor.fetchall()

        aulas = []
        for aula in registros:
            inscritos = contar_inscritos(cursor, aula[0])
            aulas.append(aula + (inscritos,))
        return render_template('grade_de_aulas.html', aulas=aulas,
                               dias_semana=DIAS_HTML)
    except Exception as erro:
        con.rollback()
        print('Erro ao carregar grade:', erro)
        flash('Não foi possível carregar a grade.', 'erro')
        return redirect(url_for('dashboard_admin'))
    finally:
        cursor.close()


# Grade do aluno: esconde aulas lotadas, exceto as já agendadas.
@app.route('/grade_aulas_aluno', methods=['GET', 'POST'])
def grade_aulas_aluno():
    if 'id_usuario' not in session:
        return redirect(url_for('login'))
    if session.get('perfil') != 3:
        flash('Acesso permitido somente ao aluno.', 'erro')
        return redirect(url_for('index'))

    id_usuario = session['id_usuario']
    cursor = con.cursor()
    try:
        if request.method == 'POST':
            acao = request.form.get('acao', 'agendar')
            try:
                id_aula = int(request.form.get('id_aula', ''))
            except ValueError:
                flash('Selecione uma aula válida.', 'erro')
                return redirect(url_for('grade_aulas_aluno'))

            if acao == 'cancelar':
                cursor.execute("""
                    DELETE FROM AGENDAMENTO
                    WHERE ID_USUARIO = ? AND ID_AULA = ?
                """, (id_usuario, id_aula))
                if cursor.rowcount:
                    con.commit()
                    flash('Agendamento cancelado com sucesso!', 'sucesso')
                else:
                    flash('Você não está inscrito nesta aula.', 'erro')
            elif acao == 'agendar':
                mensagem, categoria = realizar_agendamento(cursor, id_usuario, id_aula)
                flash(mensagem, categoria)
            else:
                flash('Ação inválida.', 'erro')
            return redirect(url_for('grade_aulas_aluno'))

        cursor.execute("""
            SELECT A.ID_AULA, M.NOME, U.NOME, A.CAPACIDADE,
                   D.DIA_SEMANA, D.HORA_INICIO, D.HORA_FIM
            FROM AULA A
            INNER JOIN MODALIDADE M ON A.ID_MODALIDADE = M.ID_MODALIDADE
            INNER JOIN USUARIO U ON A.ID_USUARIO = U.ID_USUARIO
            INNER JOIN DIA_SEMANA D ON A.ID_AULA = D.ID_AULA
            ORDER BY D.DIA_SEMANA, D.HORA_INICIO, M.NOME
        """)
        registros = cursor.fetchall()

        aulas = []
        for aula in registros:
            id_aula = aula[0]
            inscritos = contar_inscritos(cursor, id_aula)

            cursor.execute("""
                SELECT ID_AGENDAMENTO FROM AGENDAMENTO
                WHERE ID_USUARIO = ? AND ID_AULA = ?
            """, (id_usuario, id_aula))
            minha_inscricao = cursor.fetchone()

            # Mostra vagas disponíveis e aulas já agendadas.
            if inscritos < aula[3] or minha_inscricao:
                if minha_inscricao:
                    esta_inscrito = 1
                else:
                    esta_inscrito = 0
                aulas.append(aula + (inscritos, esta_inscrito))

        return render_template('grade_aulas_aluno.html', aulas=aulas,
                               dias_semana=DIAS_HTML)
    except Exception as erro:
        con.rollback()
        print('Erro na grade do aluno:', erro)
        flash('Não foi possível carregar as aulas.', 'erro')
        return redirect(url_for('index'))
    finally:
        cursor.close()


@app.route('/grade_aulas_professor')
def grade_aulas_professor():
    if 'id_usuario' not in session:
        return redirect(url_for('login'))
    if session.get('perfil') != 2:
        flash('Acesso permitido somente ao professor.', 'erro')
        return redirect(url_for('index'))

    cursor = con.cursor()
    try:
        cursor.execute("""
            SELECT M.NOME, D.DIA_SEMANA, D.HORA_INICIO, D.HORA_FIM,
                   A.CAPACIDADE, A.ID_AULA
            FROM AULA A
            INNER JOIN MODALIDADE M ON M.ID_MODALIDADE = A.ID_MODALIDADE
            INNER JOIN DIA_SEMANA D ON D.ID_AULA = A.ID_AULA
            WHERE A.ID_USUARIO = ?
            ORDER BY D.DIA_SEMANA, D.HORA_INICIO
        """, (session['id_usuario'],))
        registros = cursor.fetchall()

        aulas = []
        for nome, dia, inicio, fim, capacidade, id_aula in registros:
            inscritos = contar_inscritos(cursor, id_aula)
            aulas.append((nome, dia, inicio, fim, capacidade, inscritos))

        return render_template('grade_aulas_professor.html', aulas=aulas,
                               dias_semana=DIAS_HTML)
    except Exception as erro:
        con.rollback()
        print('Erro na grade do professor:', erro)
        flash('Não foi possível carregar as aulas.', 'erro')
        return redirect(url_for('index'))
    finally:
        cursor.close()


# Rota alternativa usada por possíveis formulários antigos.
@app.route('/agendar_aula/<int:id_aula>', methods=['POST'])
def agendar_aula(id_aula):
    if 'id_usuario' not in session:
        return redirect(url_for('login'))
    if session.get('perfil') != 3:
        flash('Somente alunos podem se inscrever.', 'erro')
        return redirect(url_for('index'))

    cursor = con.cursor()
    try:
        mensagem, categoria = realizar_agendamento(cursor, session['id_usuario'], id_aula)
        flash(mensagem, categoria)
    except Exception as erro:
        con.rollback()
        print('Erro ao realizar inscrição:', erro)
        flash('Não foi possível realizar sua inscrição.', 'erro')
    finally:
        cursor.close()
    return redirect(url_for('grade_aulas_aluno'))


# Editar Aula
@app.route('/editar_aula/<int:id_aula>', methods=['GET', 'POST'])
def editar_aula(id_aula):

    if 'id_usuario' not in session:
        flash('Faça login para acessar esta página.', 'erro')
        return redirect(url_for('login'))

    cursor = con.cursor()

    try:
        # Verifica se o usuário é administrador
        cursor.execute("""
            SELECT PERFIL
            FROM USUARIO
            WHERE ID_USUARIO = ?
        """, (session['id_usuario'],))

        usuario = cursor.fetchone()

        if not usuario or usuario[0] != 1:
            flash('Acesso permitido somente ao administrador.', 'erro')
            return redirect(url_for('index'))

        # Busca a aula
        cursor.execute("""
            SELECT ID_AULA, CAPACIDADE, ID_MODALIDADE, ID_USUARIO
            FROM AULA
            WHERE ID_AULA = ?
        """, (id_aula,))

        aula = cursor.fetchone()

        if not aula:
            flash('Aula não encontrada.', 'erro')
            return redirect(url_for('grade_de_aulas'))

        # Busca os dias e horários atuais
        cursor.execute("""
            SELECT DIA_SEMANA, HORA_INICIO, HORA_FIM
            FROM DIA_SEMANA
            WHERE ID_AULA = ?
            ORDER BY DIA_SEMANA
        """, (id_aula,))

        registros_dias = cursor.fetchall()

        dias_atuais = []
        for registro in registros_dias:
            dias_atuais.append(str(registro[0]))

        if registros_dias:
            hora_inicio_atual = str(registros_dias[0][1])[:5]
            hora_fim_atual = str(registros_dias[0][2])[:5]
        else:
            hora_inicio_atual = ''
            hora_fim_atual = ''

        # Busca modalidades e professores ativos
        cursor.execute("""
            SELECT ID_MODALIDADE, NOME
            FROM MODALIDADE
            WHERE ATIVO = 1
            ORDER BY NOME
        """)
        modalidades = cursor.fetchall()

        cursor.execute("""
            SELECT ID_USUARIO, NOME
            FROM USUARIO
            WHERE PERFIL = 2 AND ATIVO = 1
            ORDER BY NOME
        """)
        professores = cursor.fetchall()

        if request.method == 'POST':

            modalidade = request.form.get('modalidade', '').strip()
            professor = request.form.get('professor', '').strip()
            dias_selecionados = request.form.getlist('dias')
            hora_inicio = request.form.get('hora_inicio', '').strip()
            hora_fim = request.form.get('hora_fim', '').strip()
            capacidade_texto = request.form.get('capacidade', '').strip()

            if (
                not modalidade or not professor or not dias_selecionados
                or not hora_inicio or not hora_fim or not capacidade_texto
            ):
                flash('Preencha todos os campos obrigatórios.', 'erro')

            else:
                try:
                    modalidade_id = int(modalidade)
                    professor_id = int(professor)
                    capacidade = int(capacidade_texto)
                    dias = []
                    for dia in dias_selecionados:
                        dias.append(int(dia))

                except ValueError:
                    flash('Os dados informados são inválidos.', 'erro')

                else:
                    dias_invalidos = False
                    for dia in dias:
                        if dia < 1 or dia > 7 or dias.count(dia) > 1:
                            dias_invalidos = True

                    if capacidade < 1 or capacidade > 18:
                        flash('A capacidade deve estar entre 1 e 18 alunos.', 'erro')

                    elif dias_invalidos:
                        flash('Selecione dias da semana válidos.', 'erro')

                    elif not horario_valido(hora_inicio) or not horario_valido(hora_fim):
                        flash('Informe horários válidos.', 'erro')

                    elif hora_fim <= hora_inicio:
                        flash(
                            'O horário de término deve ser posterior ao início.',
                            'erro'
                        )

                    else:
                        # Confirma que a modalidade está ativa
                        cursor.execute("""
                            SELECT ID_MODALIDADE
                            FROM MODALIDADE
                            WHERE ID_MODALIDADE = ? AND ATIVO = 1
                        """, (modalidade_id,))

                        modalidade_valida = cursor.fetchone()

                        # Confirma que o professor está ativo
                        cursor.execute("""
                            SELECT ID_USUARIO
                            FROM USUARIO
                            WHERE ID_USUARIO = ?
                              AND PERFIL = 2
                              AND ATIVO = 1
                        """, (professor_id,))

                        professor_valido = cursor.fetchone()

                        if not modalidade_valida:
                            flash('Selecione uma modalidade ativa.', 'erro')

                        elif not professor_valido:
                            flash('Selecione um professor ativo válido.', 'erro')

                        else:
                            inscritos = contar_inscritos(cursor, id_aula)
                            # Confere se os dias ou horários foram alterados.
                            mudou_horario = False
                            if hora_inicio != hora_inicio_atual or hora_fim != hora_fim_atual:
                                mudou_horario = True
                            if len(dias) != len(dias_atuais):
                                mudou_horario = True
                            for dia in dias:
                                if str(dia) not in dias_atuais:
                                    mudou_horario = True
                            if capacidade < inscritos:
                                flash('A capacidade não pode ser menor que o número de alunos inscritos.', 'erro')
                                return redirect(url_for('editar_aula', id_aula=id_aula))
                            if inscritos and mudou_horario:
                                flash('Não é possível alterar os horários de uma aula que já tem alunos inscritos.', 'erro')
                                return redirect(url_for('editar_aula', id_aula=id_aula))

                            # Verifica conflitos, ignorando a própria aula
                            conflito = False

                            for dia in dias:
                                cursor.execute("""
                                    SELECT FIRST 1 A.ID_AULA
                                    FROM AULA A
                                    INNER JOIN DIA_SEMANA D
                                        ON A.ID_AULA = D.ID_AULA
                                    WHERE A.ID_USUARIO = ?
                                      AND D.DIA_SEMANA = ?
                                      AND D.HORA_INICIO < ?
                                      AND D.HORA_FIM > ?
                                      AND A.ID_AULA <> ?
                                """, (
                                    professor_id,
                                    dia,
                                    hora_fim,
                                    hora_inicio,
                                    id_aula
                                ))

                                if cursor.fetchone():
                                    conflito = True
                                    break

                            if conflito:
                                flash(
                                    'Conflito de horário! Esse professor já '
                                    'possui uma aula nesse dia e horário.',
                                    'erro'
                                )

                            else:
                                try:
                                    # Atualiza os dados principais
                                    cursor.execute("""
                                        UPDATE AULA
                                        SET CAPACIDADE = ?,
                                            ID_MODALIDADE = ?,
                                            ID_USUARIO = ?
                                        WHERE ID_AULA = ?
                                    """, (
                                        capacidade,
                                        modalidade_id,
                                        professor_id,
                                        id_aula
                                    ))

                                    # Remove os dias antigos
                                    cursor.execute("""
                                        DELETE FROM DIA_SEMANA
                                        WHERE ID_AULA = ?
                                    """, (id_aula,))

                                    # Grava os dias e horários atualizados
                                    for dia in dias:
                                        cursor.execute("""
                                            INSERT INTO DIA_SEMANA
                                                (ID_AULA, DIA_SEMANA,
                                                 HORA_INICIO, HORA_FIM)
                                            VALUES (?, ?, ?, ?)
                                        """, (
                                            id_aula,
                                            dia,
                                            hora_inicio,
                                            hora_fim
                                        ))

                                    con.commit()

                                    flash('Aula atualizada com sucesso!', 'sucesso')
                                    return redirect(url_for('grade_de_aulas'))

                                except Exception:
                                    con.rollback()
                                    raise

        # Mantém os dados enviados no formulário quando há erro
        dados_formulario = {
            'modalidade': request.form.get('modalidade', str(aula[2])),
            'professor': request.form.get('professor', str(aula[3])),
            'dias': request.form.getlist('dias') if request.method == 'POST' else dias_atuais,
            'hora_inicio': request.form.get('hora_inicio', hora_inicio_atual),
            'hora_fim': request.form.get('hora_fim', hora_fim_atual),
            'capacidade': request.form.get('capacidade', str(aula[1]))
        }

        return render_template(
            'editar_aula.html',
            aula=aula,
            modalidades=modalidades,
            professores=professores,
            dados=dados_formulario
        )

    except Exception as erro:
        con.rollback()
        print('Erro ao editar aula:', erro)
        flash('Não foi possível editar a aula.', 'erro')
        return redirect(url_for('grade_de_aulas'))

    finally:
        cursor.close()


# Excluir Aula
@app.route('/excluir_aula/<int:id_aula>', methods=['POST'])
def excluir_aula(id_aula):

    if 'id_usuario' not in session:
        flash('Faça login para acessar esta página.', 'erro')
        return redirect(url_for('login'))

    cursor = con.cursor()

    try:
        # Verifica se o usuário é administrador
        cursor.execute("""
            SELECT PERFIL
            FROM USUARIO
            WHERE ID_USUARIO = ?
        """, (session['id_usuario'],))

        usuario = cursor.fetchone()

        if not usuario or usuario[0] != 1:
            flash('Acesso permitido somente ao administrador.', 'erro')
            return redirect(url_for('index'))

        # Confirma que a aula existe
        cursor.execute("""
            SELECT ID_AULA
            FROM AULA
            WHERE ID_AULA = ?
        """, (id_aula,))

        if not cursor.fetchone():
            flash('Aula não encontrada.', 'erro')
            return redirect(url_for('grade_de_aulas'))

        cursor.execute('SELECT COUNT(*) FROM AGENDAMENTO WHERE ID_AULA = ?', (id_aula,))
        if cursor.fetchone()[0] > 0:
            flash('Não é possível excluir uma aula com inscrições. Cancele as inscrições antes.', 'erro')
            return redirect(url_for('grade_de_aulas'))

        # Exclui primeiro os dias vinculados à aula
        cursor.execute("""
            DELETE FROM DIA_SEMANA
            WHERE ID_AULA = ?
        """, (id_aula,))

        # Depois exclui a aula
        cursor.execute("""
            DELETE FROM AULA
            WHERE ID_AULA = ?
        """, (id_aula,))

        con.commit()

        flash('Aula excluída com sucesso!', 'sucesso')

    except Exception as erro:
        con.rollback()
        print('Erro ao excluir aula:', erro)
        flash('Não foi possível excluir a aula.', 'erro')

    finally:
        cursor.close()

    return redirect(url_for('grade_de_aulas'))






# Relatórios PDF solicitados para a administração.

@app.route('/relatorio_aulas/<tipo>')
def relatorio_aulas(tipo):

    if 'id_usuario' not in session:
        return redirect(url_for('login'))

    if session.get('perfil') != 1:
        flash('Somente o administrador pode gerar relatórios.', 'erro')
        return redirect(url_for('index'))

    if tipo not in ('esgotadas', 'com_vagas'):
        return redirect(url_for('dashboard_admin'))

    cursor = con.cursor()

    try:
        # Escolhe o título do relatório.
        if tipo == 'esgotadas':
            titulo = 'Relatorio de aulas esgotadas'
        else:
            titulo = 'Relatorio de aulas com vagas'

        # Busca todas as aulas no banco.
        cursor.execute("""
            SELECT M.NOME, U.NOME, D.DIA_SEMANA,
                   D.HORA_INICIO, D.HORA_FIM, A.CAPACIDADE, A.ID_AULA
            FROM AULA A
            INNER JOIN MODALIDADE M ON A.ID_MODALIDADE = M.ID_MODALIDADE
            INNER JOIN USUARIO U ON A.ID_USUARIO = U.ID_USUARIO
            INNER JOIN DIA_SEMANA D ON A.ID_AULA = D.ID_AULA
            ORDER BY M.NOME, D.DIA_SEMANA, D.HORA_INICIO
        """)
        registros = cursor.fetchall()

        # Separa as aulas esgotadas das que ainda têm vagas.
        aulas = []
        for nome, professor, dia, inicio, fim, capacidade, id_aula in registros:
            inscritos = contar_inscritos(cursor, id_aula)
            if tipo == 'esgotadas' and inscritos >= capacidade:
                aulas.append((nome, professor, dia, inicio, fim, capacidade, inscritos))
            if tipo == 'com_vagas' and inscritos < capacidade:
                aulas.append((nome, professor, dia, inicio, fim, capacidade, inscritos))

        # Cria o documento PDF
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Título do PDF
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, 'ATIVA FITNESS', ln=True, align='C')

        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, titulo, ln=True, align='C')

        pdf.ln(5)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(10)

        # Informações das aulas
        pdf.set_font('Arial', size=11)

        if not aulas:
            pdf.cell(0, 10, 'Nenhuma aula encontrada.', ln=True)

        else:
            for nome, professor, dia, inicio, fim, capacidade, inscritos in aulas:

                if dia:
                    nome_dia = DIAS_SEMANA.get(int(dia), '-')
                    horario = str(inicio)[:5] + ' ate ' + str(fim)[:5]
                else:
                    nome_dia = '-'
                    horario = '-'

                vagas = capacidade - inscritos

                pdf.multi_cell(0, 8, f'Modalidade: {nome}')
                pdf.multi_cell(0, 8, f'Professor: {professor}')
                pdf.cell(0, 8, f'Dia: {nome_dia}', ln=True)
                pdf.cell(0, 8, f'Horario: {horario}', ln=True)
                pdf.cell(0, 8, f'Inscritos: {inscritos}', ln=True)
                pdf.cell(0, 8, f'Capacidade: {capacidade}', ln=True)
                pdf.cell(0, 8, f'Vagas restantes: {max(0, vagas)}', ln=True)

                pdf.ln(8)

        # Total de registros
        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, f'Total de registros: {len(aulas)}',
                 ln=True, align='C')

        # Salva o PDF
        nome_arquivo = 'aulas_' + tipo + '.pdf'
        caminho = app.root_path + '/' + nome_arquivo

        pdf.output(caminho)

        # Envia o arquivo para download
        return send_file(
            caminho,
            as_attachment=True,
            download_name=nome_arquivo,
            mimetype='application/pdf'
        )

    except Exception as erro:
        con.rollback()
        print('Erro ao gerar PDF:', erro)
        flash('Não foi possível gerar o relatório.', 'erro')
        return redirect(url_for('dashboard_admin'))

    finally:
        cursor.close()



if __name__ == '__main__':
    app.run(debug=True)
