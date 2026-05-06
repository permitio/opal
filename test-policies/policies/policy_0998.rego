package governance.enforcement.context.verify.policy_0998

# Auto-generated policy 998 (Rego v1 syntax)
# Package: governance.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0998",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0998_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0998_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
