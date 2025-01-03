import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { HelloWorldComponent } from './hello-world/hello-world.component';
//import { UserSelectComponent } from './user-select/user-select.component';

@Component({
  selector: 'app-root',
  standalone: true,
  //imports: [RouterOutlet, UserSelectComponent],
  imports: [RouterOutlet, HelloWorldComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  title = 'opal-frontend';

  runE2ETests() {
    console.log('Running E2E tests...');
  }

  getPolicyStore(){
    return 'Your policy store value here';
  }
}


