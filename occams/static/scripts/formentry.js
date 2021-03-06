+function($){
  'use strict';

  /**
   * Check if the browser supports (and can actually validate) dates
   */
  window.supportsDateInput = +function() {
    var input = document.createElement('input');
    input.setAttribute('type','date');
    var notADateValue = 'not-a-date';
    input.setAttribute('value', notADateValue);
    return !(input.value === notADateValue);
  }();

  /**
   * Datastore client-side data entry behaviors
   */

  $.fn.formentry = function(){
    return this.each(function(){
      var $form = $(this);

      // Enable validation
      $form.validate()

      // Enable widgets
      $('.js-select2:not([data-bind])').each(function(i, element){
        // select2 doesn't check if already initialized...
        if ($(element).data('select2') === undefined){
          $(element).select2();
        }
      });

      if (!window.supportsDateInput){
          $('input[type=date]:not([data-bind]),.js-date:not([data-bind])').datetimepicker({
            pickTime: false, format: 'YYYY-MM-DD'});
          $('input[type=datetime]:not([data-bind]),.js-datetime:not([data-bind])').datetimepicker();
      }

      // Load the specified version of the form
      $form.on('change', '[name="ofmetadata_-version"]', function(event){
        $.get(window.location, {'version': event.target.value}, function(data, textStatus, jqXHR){
          var $body = $form.find('.modal-body');
          $body.children().not('.entity').remove();
          $body.append($('<hr />'));
          $body.append($(data).find('.modal-body').children());
        });
      });

      // Disable all fields if not done is checked
      $form.on('change', '[name="ofmetadata_-not_done"]', function(event){
          $form.validate().resetForm();
        $('.form-group', $form).removeClass('alert alert-danger has-error has-success');
        $('.errors').empty();
        $('.ds-widget', $form).prop('disabled', event.target.checked);
      });


      $form.on('click', '.js-fileinput-previous', function(event){
        var $target = $(event.target),
            $new = $($target.data('fileinput-new'));
            ;
        if ($target.prop('checked')){
          $new.fileinput('clear');
        }
      });

      $form.on('change filecleared', '.js-fileinput-new', function(event){
          var $target = $(event.target),
              $previous = $($target.data('fileinput-previous'))
              ;
          $previous.prop('checked', !$target.val());
        });
    });
  };

  $(function(){
    $('.js-formentry').formentry();
  });

  ko.bindingHandlers.formentry = {
    init: function(element, valueAccessor, allBindingsAccessor) {
      $(element).formentry();
    }
  };

}(jQuery);
