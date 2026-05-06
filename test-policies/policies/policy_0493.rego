package governance.authentication.policy.deny.policy_0493

# Auto-generated policy 493 (Rego v1 syntax)
# Package: governance.authentication.policy.deny

# Metadata
metadata := {
    "policy_id": "0493",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0493_allowed = false
policy_0493_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0493_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0493_allowed if {
    data.policies.governance.enabled
}
