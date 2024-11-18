import { ComponentFixture, TestBed } from '@angular/core/testing';

import { SelectPolicyRepoComponent } from './select-policy-repo.component';

describe('SelectPolicyRepoComponent', () => {
  let component: SelectPolicyRepoComponent;
  let fixture: ComponentFixture<SelectPolicyRepoComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SelectPolicyRepoComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(SelectPolicyRepoComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
