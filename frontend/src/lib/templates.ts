// Starter-code templates shown on workspace creation. Picked by language.

export interface Template {
  id:          string;
  language:    string;     // backend executor language
  monaco:      string;     // Monaco tokenizer language
  label:       string;
  description: string;
  code:        string;
}

export const TEMPLATES: Template[] = [
  // ── Python ──────────────────────────────────────────────────────────────
  {
    id: 'py-hello', language: 'python', monaco: 'python',
    label: 'Python · Hello',
    description: 'Minimal starter',
    code:
`# Welcome to ASTRA-IDE
def greet(name: str) -> str:
    return f"Hello, {name}!"

print(greet("ASTRA"))
`,
  },
  {
    id: 'py-fizzbuzz', language: 'python', monaco: 'python',
    label: 'Python · FizzBuzz',
    description: 'Classic interview prep',
    code:
`for i in range(1, 21):
    if i % 15 == 0:
        print("FizzBuzz")
    elif i % 3 == 0:
        print("Fizz")
    elif i % 5 == 0:
        print("Buzz")
    else:
        print(i)
`,
  },
  {
    id: 'py-ml', language: 'python', monaco: 'python',
    label: 'Python · ML quickstart',
    description: 'sklearn imports + dataset shell',
    code:
`# (sklearn is not pre-installed in the demo executor; pip install if needed)
import random

# Toy dataset
rng = random.Random(42)
X = [[rng.random(), rng.random()] for _ in range(20)]
y = [int(a + b > 1.0) for a, b in X]

# Simple decision: predict via threshold
correct = sum(1 for (a, b), label in zip(X, y) if int(a + b > 1.0) == label)
print(f"Accuracy: {correct/len(X):.2%}")
`,
  },

  // ── C++ ─────────────────────────────────────────────────────────────────
  {
    id: 'cpp-hello', language: 'cpp', monaco: 'cpp',
    label: 'C++ · Hello',
    description: 'C++17 starter',
    code:
`#include <iostream>
#include <string>

int main() {
    std::string name = "ASTRA";
    std::cout << "Hello, " << name << "!\\n";
    return 0;
}
`,
  },
  {
    id: 'cpp-stl', language: 'cpp', monaco: 'cpp',
    label: 'C++ · STL containers',
    description: 'vector + sort + algorithm',
    code:
`#include <iostream>
#include <vector>
#include <algorithm>

int main() {
    std::vector<int> v = {5, 2, 9, 1, 5, 6};
    std::sort(v.begin(), v.end());
    for (int x : v) std::cout << x << " ";
    std::cout << "\\n";
}
`,
  },

  // ── JavaScript ──────────────────────────────────────────────────────────
  {
    id: 'js-hello', language: 'javascript', monaco: 'javascript',
    label: 'JavaScript · Hello',
    description: 'Node.js starter',
    code:
`const greet = (name) => \`Hello, \${name}!\`;
console.log(greet('ASTRA'));
`,
  },
  {
    id: 'js-fetch', language: 'javascript', monaco: 'javascript',
    label: 'JavaScript · async/await',
    description: 'Sample data pipeline',
    code:
`async function pipeline(items) {
  return items
    .map(x => x * 2)
    .filter(x => x > 5)
    .reduce((a, b) => a + b, 0);
}

pipeline([1, 2, 3, 4, 5]).then(total => console.log('total:', total));
`,
  },

  // ── Bash ────────────────────────────────────────────────────────────────
  {
    id: 'sh-hello', language: 'bash', monaco: 'shell',
    label: 'Bash · Hello',
    description: 'Shell starter',
    code:
`#!/bin/bash
echo "Hello from ASTRA-IDE"
date
uname -a 2>/dev/null || true
`,
  },
];

export function templatesForLanguage(lang: string): Template[] {
  return TEMPLATES.filter((t) => t.language === lang);
}

export function defaultTemplateFor(lang: string): Template | undefined {
  return templatesForLanguage(lang)[0];
}
