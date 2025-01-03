import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private users = {
    "alice": 'JWT_TOKEN_FOR_ALICE',
    "bob": 'JWT_TOKEN_FOR_BOB'
  };

  constructor(private http: HttpClient) {}

  setHeaders(user: string): HttpHeaders {
    const token = this.users[user as keyof typeof this.users];;
    return new HttpHeaders({
      Authorization: `Bearer ${token}`
    });
  }

  callEndpoint(endpoint: string, user: string): Observable<any> {
    return this.http.get(`http://sample_service:5500/${endpoint}`, {
      headers: this.setHeaders(user)
    });
  }
}