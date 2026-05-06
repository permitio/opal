package risk.validation.action.verify.policy_0346

# Auto-generated policy 346 (Rego v1 syntax)
# Package: risk.validation.action.verify

# Metadata
metadata := {
    "policy_id": "0346",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0346_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0346_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
