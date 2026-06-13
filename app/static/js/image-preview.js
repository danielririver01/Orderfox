/**
 * Image Preview & Removal Shared Logic
 * Used by product_form.html and category_form.html
 */
function previewImage(input) {
  const container = document.getElementById('image_preview_container');
  const placeholder = document.getElementById('placeholder_icon');
  const preview = document.getElementById('new_preview');
  const removeBtn = document.getElementById('remove_image_btn');
  const deleteInput = document.getElementById('delete_image_input');
  const originalImg = document.getElementById('original_img');
  const editOverlay = document.getElementById('edit_overlay');

  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = function (e) {
      preview.src = e.target.result;
      preview.classList.remove('hidden');
      if (placeholder) placeholder.classList.add('hidden');
      if (originalImg) originalImg.classList.add('hidden');
      if (editOverlay) editOverlay.classList.add('hidden');
      removeBtn.classList.remove('hidden');
      container.classList.remove('border-dashed');
      deleteInput.value = 'false';
    }
    reader.readAsDataURL(input.files[0]);
  }
}

function removeImage() {
  const input = document.querySelector('.image-upload-input');
  const preview = document.getElementById('new_preview');
  const placeholder = document.getElementById('placeholder_icon');
  const removeBtn = document.getElementById('remove_image_btn');
  const deleteInput = document.getElementById('delete_image_input');
  const originalImg = document.getElementById('original_img');
  const editOverlay = document.getElementById('edit_overlay');
  const container = document.getElementById('image_preview_container');

  input.value = '';
  preview.classList.add('hidden');
  preview.src = '';

  if (originalImg) {
    originalImg.classList.add('hidden');
    if (editOverlay) editOverlay.classList.add('hidden');
    deleteInput.value = 'true';
  }

  if (placeholder) placeholder.classList.remove('hidden');
  removeBtn.classList.add('hidden');
  container.classList.add('border-dashed');
}

// Event delegation handlers
window.actionHandlers = window.actionHandlers || {};
window.actionHandlers.formImagePreview = () => document.querySelector('.image-upload-input')?.click();
window.actionHandlers.removeImage = removeImage;
window.actionHandlers.openDeleteModal = (p) => openDeleteModal(document.getElementById(p.form), p.message, p.title);
