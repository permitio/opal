import { Component } from '@angular/core';
import { AuthService } from '../auth.service';

@Component({
  selector: 'app-dropdown',
  templateUrl: './dropdown.component.html',
  styleUrls: ['./dropdown.component.css']
})
export class DropdownComponent {
  selectedUser: string = '';
  users: string[] = ['alice', 'bob'];

  constructor(private authService: AuthService) {}

  onUserSelect(user: string) {
    this.selectedUser = user;
  }

  callEndpoint(endpoint: string) {
    if (!this.selectedUser) {
      alert('Please select a user first!');
      return;
    }
    this.authService.callEndpoint(endpoint, this.selectedUser).subscribe(
      response => {
        console.log(`Response from ${endpoint}:`, response);
      },
      error => {
        console.error(`Error from ${endpoint}:`, error);
      }
    );
  }
}