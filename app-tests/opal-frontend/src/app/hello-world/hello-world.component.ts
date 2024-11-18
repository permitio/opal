import { Component } from '@angular/core';

@Component({
  selector: 'app-hello-world',
  standalone: true,
  imports: [],
  templateUrl: './hello-world.component.html',
  styleUrls: ['./hello-world.component.css']
})
export class HelloWorldComponent {
  // Define the initial caption
  buttonCaption = 'Click me!';

  // Function to change the caption when the button is clicked
  changeCaption() {
    this.buttonCaption = this.buttonCaption === 'Click me!' ? 'You clicked me!' : 'Click me!';
  }
}