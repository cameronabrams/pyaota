HEADMATTER = r"""
\documentclass[12pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{fancyhdr}
\usepackage{setspace}
\usepackage{enumitem}
\usepackage{verbatim}
\usepackage{listings}
\usepackage{xcolor}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{upquote}
\usepackage[scaled]{helvet}
\renewcommand\familydefault{\sfdefault}
\usepackage{pifont}
\usepackage{tikz}
\usetikzlibrary{calc}
\usepackage{qrcode}
\usepackage{multicol}

% Version label + QR macros (filled in by Python)
\newcommand{\ExamVersionLabel}{<<VERSION_LABEL>>}
\newcommand{\ExamQR}{\qrcode[height=1.5cm]{<<VERSION_QR_TEXT>>}}
\newcommand{\Instructions}{<<INSTRUCTIONS>>}
\definecolor{bubblegray}{gray}{0.45} 
\newcommand{\circledletter}[1]{%
  \tikz[baseline=-0.6ex]{%
    \node[
      circle,
      draw,
      inner sep=0pt,
      minimum size=1.1em,      % slightly larger bubble
      font=\footnotesize,   % <-- larger than scriptsize
      text height=1.5ex,       % fixed bounding box height
      text depth=0.4ex,        % fixed bounding box depth
      anchor=center
    ] {\textcolor{bubblegray}{#1}};
  }%
}

\newcommand{\idbox}{%
  \tikz[baseline=-0.6ex]{
    \node[draw, minimum width=0.7cm, minimum height=0.7cm] (box) {};
  }%
}

\newcommand{\idboxes}[1][8]{%
  \foreach \i in {1,...,#1}{\idbox\hspace{0.15cm}}%
}

\newcommand{\correctlabel}[1]{%
  \tikz[baseline=(char.base)]{
    \node[
      circle,
      fill=black,
      draw=black,
      inner sep=0pt,
      minimum size=1.0em,
      font=\normalsize
    ] (char) {\textcolor{white}{#1}};
  }%
}

\definecolor{lightlightgray}{gray}{0.9}\lstdefinestyle{mypython}{
  language=Python,
  basicstyle=\ttfamily\small,
  showstringspaces=false,
  breaklines=true,
  upquote=true,
  commentstyle=\ttfamily\upshape,
}
\newcommand{\inl}[1]{\lstinline[style=mypython]|#1|}
\lstdefinestyle{pseudocode}{
    basicstyle=\ttfamily,
    keywordstyle=\bfseries,
    keywords={if,then,else,elseif,while,for,return,end,endif,endwhile,endfor,print},
    columns=fullflexible,
    frame=single,
    mathescape=true,
    escapechar=§
}

\newcommand{\blank}[1][2cm]{\underline{\hspace{#1}}}
\newcommand{\smallblank}[1][0.5cm]{\ \underline{\hspace{#1}}\ }

\newif\ifshowanswers
\showanswersfalse

\newcounter{mcq}

\newenvironment{mcq}[3]{%
  \refstepcounter{mcq}%
  \par\medskip
  \def\mcqid{#1}%
  \def\mcqpoints{#2}%
  \def\mcqcorrect{#3}%
  \noindent\begin{minipage}{\linewidth}%
    \textbf{\themcq.}\enspace
}{%
  \end{minipage}%
  \par\bigskip
  \par\bigskip
}

\newenvironment{choices}{%
  \begin{enumerate}[label=\alph*., leftmargin=2em]
}{%
  \end{enumerate}
}

\newcommand{\choice}[2][]{%
  \item[#1] #2%
}

\newcommand{\choicecode}[1][]{%
  \item[#1]
}

\pagestyle{fancy}
\fancyhf{}
\rhead{Drexel University -- ENGR 131 --- Winter 2025-2026}
\lhead{Midterm Exam}
\rfoot{\thepage}

% Special pagestyle for answer sheet: same header, no footer / page number
\fancypagestyle{answersheet}{%
  \fancyhf{}%
  \rhead{Drexel University -- ENGR 131 --- Winter 2025-2026}%
  \lhead{Midterm Exam}%
}


\begin{document}

"""

DEFAULT_EXAM_INSTRUCTIONS = r"""
\begin{enumerate}
\item \textbf{Carefully} detach the answer sheet from the back of this exam packet.
\item Enter your name and student ID number on the answer sheet in the spaces provided.
\item Fill in the bubbles on the answer sheet corresponding to your answers.  Use a \textbf{No. 2 pencil} only.
\item Time allowed: 50 minutes.
\item No calculators, notes, textbooks, or other aids are permitted.
\item \textbf{Turn in only your answer sheet}.  You should keep your exam packet.
\end{enumerate}
"""

DEFAULT_ANSWER_SHEET_INSTRUCTIONS = r"""

Your name: \underline{\hspace{9cm}}\\*[0.4em]

Your Drexel Student ID: \idboxes[8]\\*[0.4em]

Please fill in one bubble per question.  Make sure you turn this answer sheet in to a TA or instructor at the end of the exam.
"""

def make_qr_header_instructions(instructions: str = DEFAULT_EXAM_INSTRUCTIONS) -> str:
    return r"""
% ---- Version label + QR on first page ----
\begin{minipage}{0.75\linewidth}
\begin{flushleft}
<<INSTRUCTIONS>>
\end{flushleft}
\end{minipage}
\begin{minipage}{0.24\linewidth}
\begin{flushright}
  \textbf{Version: \ExamVersionLabel}\\[0.5em]
  \ExamQR
\end{flushright}
\end{minipage}
\vspace{1em}
""".replace("<<INSTRUCTIONS>>", instructions)

ENDMESSAGE = r"""
\begin{center}
    \textbf{End of Exam}
\end{center}
"""

TAILMATTER = r"""

\end{document}
"""
