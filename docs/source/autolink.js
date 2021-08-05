/**
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

function autolink() {
  // Every type defined in these docs has a hash that can be linked to to see
  // its fields or enum values.  But Sphinx isn't linking to them automatically.
  // This may be caused by a missing Sphinx plugin, but since we heavily
  // post-process the generated type info for our config docs (see
  // docs/source/conf.py), it is easiest to add these links here.
  const linkMap = new Map();

  for (const element of document.querySelectorAll('.sig-name')) {
    const previousElement = element.previousElementSibling;
    if (previousElement && previousElement.classList.contains('sig-prename')) {
      const shortName = element.textContent;
      const longName = previousElement.textContent + element.textContent;
      const link = `<a class="reference internal" href="#${longName}">` +
          `${shortName}</a>`;
      linkMap.set(shortName, link);
    }
  }

  const propertyElements = document.querySelectorAll('.property');
  for (const [shortName, link] of linkMap) {
    // A regex that matches the name with word boundaries, so "Input" doesn't
    // match "InputType".
    const regex = new RegExp(`\\b${shortName}\\b`);

    for (const element of propertyElements) {
      if (regex.exec(element.textContent)) {
        element.innerHTML = element.innerHTML.replace(regex, link);
      }
    }
  }
}

document.addEventListener('DOMContentLoaded', autolink);
