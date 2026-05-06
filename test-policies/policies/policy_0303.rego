package audit.authentication.action.verify.logic.policy_0303

# Auto-generated policy 303 (Rego v1 syntax)
# Package: audit.authentication.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0303",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0303_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0303_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
