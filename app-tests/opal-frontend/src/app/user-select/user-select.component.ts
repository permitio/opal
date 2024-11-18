import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
// import { ApiService } from '../api.service';

@Component({
  selector: 'app-user-select',
  templateUrl: './user-select.component.html', 
  styleUrls: ['./user-select.component.css'],
  standalone: true,
  imports: [CommonModule, FormsModule] // If needed, you can import other modules here like FormsModule, HttpClientModule, etc.
})
export class UserSelectComponent {
  selectedUserToken: string | undefined;
  users = [
    { name: 'Alice', token: 'JWT_TOKEN_FOR_ALICE' },
    { name: 'Bob', token: 'JWT_TOKEN_FOR_BOB' }
  ];

  //constructor(private apiService: ApiService) {}
  constructor() {}

  // Example of calling an endpoint when a user is selected
  onSelectUser(user: any) {
    this.selectedUserToken = user.token;

    // Call endpoint A
    // this.apiService.callEndpointA(this.selectedUserToken ?? '').subscribe(response => {
    //   console.log('Response from endpoint A:', response);
    // });
  }
}