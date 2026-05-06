package governance.validation.resource.allow.policy_0704

# Auto-generated policy 704 (Rego v1 syntax)
# Package: governance.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0704",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0704_allowed if {
    input.user.role == "admin"
}
default policy_0704_allowed = false
policy_0704_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0704_allowed if {
    data.policies.governance.enabled
}
