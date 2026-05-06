package governance.enforcement.action.verify.policy_0798

# Auto-generated policy 798 (Rego v1 syntax)
# Package: governance.enforcement.action.verify

# Metadata
metadata := {
    "policy_id": "0798",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0798_allowed = false
policy_0798_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0798_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
