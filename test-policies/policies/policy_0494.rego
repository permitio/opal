package audit.validation.resource.verify.data.policy_0494

# Auto-generated policy 494 (Rego v1 syntax)
# Package: audit.validation.resource.verify.data

# Metadata
metadata := {
    "policy_id": "0494",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0494_allowed = false
policy_0494_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0494_allowed if {
    input.user.role == "admin"
}
