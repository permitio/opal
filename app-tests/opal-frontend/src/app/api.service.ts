import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  constructor(private http: HttpClient) {}

  private createHeaders(token: string) {
    return new HttpHeaders().set('Authorization', `Bearer ${token}`);
  }

  callEndpointA(token: string) {
    return this.http.get('/api/endpointA', { headers: this.createHeaders(token) });
  }

  callEndpointB(token: string) {
    return this.http.get('/api/endpointB', { headers: this.createHeaders(token) });
  }

  callEndpointC(token: string) {
    return this.http.get('/api/endpointC', { headers: this.createHeaders(token) });
  }
}