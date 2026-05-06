package governance.enforcement.user.validate.data.policy_0241

# Auto-generated policy 241 (Rego v1 syntax)
# Package: governance.enforcement.user.validate.data

# Metadata
metadata := {
    "policy_id": "0241",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0241_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0241_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
