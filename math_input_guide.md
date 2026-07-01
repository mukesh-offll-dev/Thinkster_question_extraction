# Thinkster Automator Answer Input Formatting Guide

This guide explains how to format answers in the `worksheet_answers.json` file. The question-answering automation script supports multiple question types, from simple multiple-choice questions to complex LaTeX formulas.

---

## 1. Multiple Choice Questions (MCQ)
For standard multiple-choice questions (A, B, C, D), specify the correct letter option as a uppercase string.

### JSON Syntax
```json
{
  "worksheet_id": {
    "1": "A",
    "2": "C"
  }
}
```

---

## 2. True/False Matrix Tables
For questions containing a table of rows with True/False or Yes/No radio buttons, specify the answers as a list of strings/booleans corresponding to the rows from top to bottom.

- Use `"True"` (or `"Yes"`, `"Y"`, `"T"`) for the first column button.
- Use `"False"` (or `"No"`, `"N"`, `"F"`) for the second column button.

### JSON Syntax
```json
{
  "worksheet_id": {
    "3": ["True", "False", "True", "False"]
  }
}
```

---

## 3. Basic Numerical & Text Inputs
For simple text or integer entries, write the exact number or text as a string value.

### JSON Syntax
```json
{
  "worksheet_id": {
    "4": "90",
    "5": "hello"
  }
}
```

---

## 4. Advanced Mathematical Expressions (MathQuill / LaTeX)
Since the automation tool has direct **MathQuill JS LaTeX integration**, you can write advanced mathematical formulas in LaTeX format. This bypasses keyboard layout limitations and ensures math equations are entered with 100% precision.

### Exponents & Powers
Use standard LaTeX carat notation (`^`) for superscripts.
- For $x^2$, use: `"x^2"`
- For $e^{x+1}$, use braces for multi-character exponents: `"e^{x+1}"`

### Fractions
Use the LaTeX fraction command `\frac{numerator}{denominator}`.
- For $\frac{3}{4}$, use: `"\frac{3}{4}"`
- For $\frac{x+2}{y^2}$, use: `"\frac{x+2}{y^2}"`

### Square Roots & Radicals
Use the LaTeX root command `\sqrt{value}`.
- For $\sqrt{5}$, use: `"\sqrt{5}"`
- For $\sqrt{x^2 + y^2}$, use: `"\sqrt{x^2 + y^2}"`

### Parentheses & Brackets
Use standard parenthesis and bracket keys directly.
- For $(x+2)(x-3)$, use: `"(x+2)(x-3)"`
- For $[2, 5)$, use: `"[2, 5)"`

### Example Advanced Math JSON
```json
{
  "AQCONAL202": {
    "1": "A",
    "2": "5",
    "3": ["True", "True", "True", "True"],
    "4": "\frac{x+3}{y^2}",
    "5": "\sqrt{25} + (a+b)^2"
  }
}
```

> [!NOTE]
> When writing backslashes (`\`) inside JSON strings, make sure to escape them as `\\` if you are writing JSON directly in code (e.g. `"\\frac{x}{y}"`), or write standard single backslashes `\` if editing the `.json` file in a standard editor like VS Code which handles JSON validation.
